use std::{
    io::BufReader,
    sync::mpsc::{channel, Sender},
    thread,
};

use hdf5_metno::{types::IntSize, ByteReader, Dataset, Hyperslab, Selection, SliceOrIndex};
use image::ImageFormat;
use ndarray::{s, Array2, Array3, ArrayD, Axis};
use ratatui::{
    layout::{Constraint, Layout, Rect},
    style::Style,
    Frame,
};
use ratatouille_image::{
    picker::Picker,
    thread::{ResizeRequest, ResizeResponse, ThreadProtocol},
    Resize, StatefulImage,
};

use crate::{
    error::AppError,
    h5f::{H5FNode, ImageType, InterlaceMode, Node},
    ui::preload::{CachedDataset, SharedCache},
};

use super::{
    app::AppEvent,
    dims::{render_dim_selector_with_mode, DimSelectorMode},
    segment_scroll::render_segment_scroll,
    state::{AppState, SegmentType},
};

pub fn render_img(
    image_type: &ImageType,
    f: &mut Frame,
    area: &Rect,
    // node: &Node,
    selected_node_refc: &mut H5FNode,
    state: &mut AppState,
) -> Result<(), AppError> {
    let node = &selected_node_refc.node;
    let area = if let SegmentType::Image = state.segment_state.segumented {
        let areas_split =
            Layout::horizontal(vec![Constraint::Min(1), Constraint::Length(2)]).split(*area);
        render_segment_scroll(f, &areas_split[1], state)?;
        let areas_split =
            Layout::vertical(vec![Constraint::Length(1), Constraint::Min(2)]).split(areas_split[0]);
        // center styles
        let idx = state.segment_state.idx + 1;
        let segment_count = state.segment_state.segment_count;
        let block = ratatui::widgets::Block::default()
            .title(format!(" Image {}/{} ", idx, segment_count))
            .title_alignment(ratatui::layout::Alignment::Center)
            .borders(ratatui::widgets::Borders::TOP)
            .border_type(ratatui::widgets::BorderType::Plain)
            .style(Style::default().fg(ratatui::style::Color::DarkGray));

        f.render_widget(block, areas_split[0]);
        areas_split[1]
    } else {
        *area
    };
    match image_type {
        ImageType::Jpeg => render_raw_img(f, &area, node, state, ImageFormat::Jpeg),
        ImageType::Png => render_raw_img(f, &area, node, state, ImageFormat::Png),
        ImageType::Truecolor(m) => {
            render_ds_img(f, &area, selected_node_refc, state, ImageType::Truecolor(m.clone()))
        }
        ImageType::Grayscale => render_ds_img(f, &area, selected_node_refc, state, ImageType::Grayscale),
        _ => render_unsupported_image_format(f, &area, node),
    }
}

fn render_unsupported_image_format(
    f: &mut Frame,
    area: &Rect,
    selected_node: &Node,
) -> Result<(), AppError> {
    let (ds, _) = match selected_node {
        Node::Dataset(ds, attr) => (ds, attr),
        _ => return Ok(()),
    };

    let inner_area = area.inner(ratatui::layout::Margin {
        horizontal: 2,
        vertical: 1,
    });
    let unsupported_msg = format!("Unsupported image format for dataset: {}", ds.name());
    f.render_widget(unsupported_msg, inner_area);
    Ok(())
}

fn render_ds_img(
    f: &mut Frame,
    area: &Rect,
    node: &mut H5FNode,
    state: &mut AppState,
    img_type: ImageType,
) -> Result<(), AppError> {
    let dsattr = match &node.node {
        Node::Dataset(_, attr) => attr.clone(),
        _ => return Ok(()),
    };

    let shape = &dsattr.shape;
    let ndim = shape.len();
    let ds_path = &dsattr.full_path;

    // Render dim selector above the image if ndim >= 3
    let img_area = if ndim >= 3 {
        let dim_height = if dsattr.affine.is_some() { 5 } else { 4 };
        let areas_split =
            Layout::vertical(vec![Constraint::Length(dim_height), Constraint::Min(1)]).split(*area);
        render_dim_selector_with_mode(f, &areas_split[0], node, shape, DimSelectorMode::Image)?;
        areas_split[1]
    } else {
        *area
    };

    // If multi-image mode is active, split the area and render each image
    if state.multi_image_mode && !state.multi_image_siblings.is_empty() {
        return render_multi_image(f, &img_area, node, state, img_type);
    }

    // Split image area: main image + optional colorbar for grayscale
    let (img_area, colorbar_area) = if matches!(img_type, ImageType::Grayscale) {
        let splits = Layout::horizontal(vec![
            Constraint::Min(1),
            Constraint::Length(5),
        ])
        .split(img_area);
        (splits[0], Some(splits[1]))
    } else {
        (img_area, None)
    };

    let inner_area = img_area.inner(ratatui::layout::Margin {
        horizontal: 2,
        vertical: 1,
    });

    let h_dim = node.selected_row;
    let w_dim = node.selected_col;
    let indexes: Vec<usize> = node.selected_indexes[..ndim].to_vec();

    // Initialize selected_dim to first non-H/W dim only on first load of this dataset
    let is_first_load = state.img_state.ds.as_ref() != Some(ds_path);
    if ndim >= 3 && is_first_load && (node.selected_dim == h_dim || node.selected_dim == w_dim) {
        node.selected_dim = (0..ndim).find(|&d| d != h_dim && d != w_dim).unwrap_or(0);
    }

    // First time seeing this dataset — trigger initial load (no HDF5 handles sent)
    if is_first_load {
        state.img_state.protocol = None;
        state.img_state.error = None;
        state.img_state.ds = Some(ds_path.clone());
        state.segment_state.segumented = SegmentType::NoSegment;
        state.img_state.indexes_loaded = indexes.clone();
        state.img_state.indexes_to_load = indexes.clone();
        state.img_state.img_dims_loaded = (h_dim, w_dim);
        state.img_state.idx_loaded = state.img_state.idx_to_load;
        let wl = if !state.auto_window {
            state.window_center.zip(state.window_width).map(|(c, w)| WindowLevel { center: c, width: w })
        } else {
            None
        };
        state.img_state.tx_load_img.send((
            dsattr.filename.clone(),
            ds_path.clone(),
            indexes,
            (h_dim, w_dim),
            img_type,
            wl,
        ))?;
    }

    // Render: show current image, error, or loading indicator
    if let Some(e) = &state.img_state.error {
        let error_msg = format!("Error loading image: {}", e);
        f.render_widget(error_msg, inner_area);
    } else if let Some(ref mut protocol) = state.img_state.protocol {
        let image_widget = StatefulImage::new().resize(Resize::Scale(None));
        f.render_stateful_widget(image_widget, inner_area, protocol);
    }

    // Render colorbar for grayscale images
    if let Some(cb_area) = colorbar_area {
        render_colorbar(f, &cb_area, state);
    }

    Ok(())
}

/// Render multiple images side-by-side in multi-image mode.
fn render_multi_image(
    f: &mut Frame,
    area: &Rect,
    node: &mut H5FNode,
    state: &mut AppState,
    img_type: ImageType,
) -> Result<(), AppError> {
    let dsattr = match &node.node {
        Node::Dataset(_, attr) => attr.clone(),
        _ => return Ok(()),
    };
    let ndim = dsattr.shape.len();
    let h_dim = node.selected_row;
    let w_dim = node.selected_col;
    let indexes: Vec<usize> = node.selected_indexes[..ndim].to_vec();

    let n_siblings = state.multi_image_siblings.len();
    let total_images = 1 + n_siblings; // primary + siblings

    // Layout: 1 row for <=2, 2x2 grid for 3-4
    let grid_areas = if total_images <= 2 {
        Layout::horizontal(
            std::iter::repeat(Constraint::Ratio(1, total_images as u32))
                .take(total_images)
                .collect::<Vec<_>>(),
        )
        .split(*area)
        .to_vec()
    } else {
        let rows = Layout::vertical(vec![Constraint::Ratio(1, 2), Constraint::Ratio(1, 2)])
            .split(*area);
        let cols_per_row = (total_images + 1) / 2;
        let top_cols = Layout::horizontal(
            std::iter::repeat(Constraint::Ratio(1, cols_per_row as u32))
                .take(cols_per_row.min(total_images))
                .collect::<Vec<_>>(),
        )
        .split(rows[0]);
        let bot_count = total_images.saturating_sub(cols_per_row);
        let bot_cols = if bot_count > 0 {
            Layout::horizontal(
                std::iter::repeat(Constraint::Ratio(1, bot_count as u32))
                    .take(bot_count)
                    .collect::<Vec<_>>(),
            )
            .split(rows[1])
            .to_vec()
        } else {
            vec![]
        };
        let mut all = top_cols.to_vec();
        all.extend(bot_cols);
        all
    };

    // Render primary image in first cell
    if let Some(&primary_area) = grid_areas.first() {
        let ds_path = &dsattr.full_path;
        let is_first_load = state.img_state.ds.as_ref() != Some(ds_path);
        if is_first_load {
            state.img_state.protocol = None;
            state.img_state.error = None;
            state.img_state.ds = Some(ds_path.clone());
            state.segment_state.segumented = SegmentType::NoSegment;
            state.img_state.indexes_loaded = indexes.clone();
            state.img_state.indexes_to_load = indexes.clone();
            state.img_state.img_dims_loaded = (h_dim, w_dim);
            state.img_state.idx_loaded = state.img_state.idx_to_load;
            let wl = if !state.auto_window {
                state
                    .window_center
                    .zip(state.window_width)
                    .map(|(c, w)| WindowLevel { center: c, width: w })
            } else {
                None
            };
            state.img_state.tx_load_img.send((
                dsattr.filename.clone(),
                ds_path.clone(),
                indexes.clone(),
                (h_dim, w_dim),
                img_type.clone(),
                wl,
            ))?;
        }
        // Render label + primary image
        let label = dsattr
            .full_path
            .rsplit_once('/')
            .map(|(_, n)| n)
            .unwrap_or(&dsattr.full_path);
        render_image_cell(f, &primary_area, label, &mut state.img_state.protocol);
    }

    // Initialize load workers for siblings if needed, then trigger loads
    for i in 0..state.multi_image_siblings.len().min(grid_areas.len().saturating_sub(1)) {
        // Lazily create load worker if not yet initialized
        if state.multi_image_siblings[i].tx_load.is_none() {
            if let (Some(ref tx_events), Some(ref tx_resize)) =
                (&state.img_state.tx_events, &state.img_state.tx_resize)
            {
                let tx = handle_multi_image_load(
                    i,
                    tx_events.clone(),
                    tx_resize.clone(),
                    state.img_state.picker.clone(),
                    state.preload_cache.clone(),
                );
                state.multi_image_siblings[i].tx_load = Some(tx);
            }
        }

        // Trigger load if indexes changed
        let needs_load = state.multi_image_siblings[i].loaded_indexes != indexes;
        if needs_load {
            if let Some(ref tx) = state.multi_image_siblings[i].tx_load {
                let wl = if !state.auto_window {
                    state
                        .window_center
                        .zip(state.window_width)
                        .map(|(c, w)| WindowLevel { center: c, width: w })
                } else {
                    None
                };
                let _ = tx.send((
                    state.multi_image_siblings[i].filename.clone(),
                    state.multi_image_siblings[i].ds_path.clone(),
                    indexes.clone(),
                    (h_dim, w_dim),
                    state.multi_image_siblings[i].img_type.clone(),
                    wl,
                ));
            }
        }
    }

    // Render sibling images
    for (i, sibling_area) in grid_areas.iter().skip(1).enumerate() {
        if i >= state.multi_image_siblings.len() {
            break;
        }
        let label = state.multi_image_siblings[i]
            .ds_path
            .rsplit_once('/')
            .map(|(_, n)| n.to_string())
            .unwrap_or_else(|| state.multi_image_siblings[i].ds_path.clone());
        render_image_cell(
            f,
            sibling_area,
            &label,
            &mut state.multi_image_siblings[i].protocol,
        );
    }

    Ok(())
}

/// Render a single image cell with a label at the top.
fn render_image_cell(
    f: &mut Frame,
    area: &Rect,
    label: &str,
    protocol: &mut Option<ThreadProtocol>,
) {
    use ratatui::text::Line;
    use ratatui::widgets::{Block, BorderType, Borders};

    let block = Block::default()
        .title(format!(" {} ", label))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(ratatui::style::Color::DarkGray));
    let inner = block.inner(*area);
    f.render_widget(block, *area);

    if let Some(ref mut proto) = protocol {
        let image_widget = StatefulImage::new().resize(Resize::Scale(None));
        f.render_stateful_widget(image_widget, inner, proto);
    } else {
        let loading = Line::from("Loading...");
        f.render_widget(loading, inner);
    }
}

fn render_raw_img(
    f: &mut Frame,
    area: &Rect,
    selected_node: &Node,
    state: &mut AppState,
    img_format: ImageFormat,
) -> Result<(), AppError> {
    let (ds, dsattr) = match selected_node {
        Node::Dataset(ds, attr) => (ds, attr),
        _ => return Ok(()),
    };

    let inner_area = area.inner(ratatui::layout::Margin {
        horizontal: 2,
        vertical: 1,
    });

    let is_same_ds = state.img_state.ds.as_deref() == Some(dsattr.full_path.as_str());
    if is_same_ds {
        // Already loaded or loading — just render what we have
        if let Some(ref e) = state.img_state.error {
            let error_msg = format!("Error loading image - {}", e);
            f.render_widget(error_msg, inner_area);
        } else if let Some(ref mut protocol) = state.img_state.protocol {
            let image_widget = StatefulImage::new().resize(Resize::Scale(None));
            f.render_stateful_widget(image_widget, inner_area, protocol);
        }
    } else {
        // First time — trigger load (HDF5 calls only on initial encounter)
        state.img_state.protocol = None;
        state.img_state.ds = Some(dsattr.full_path.clone());
        let typedesc = ds
            .dtype()
            .expect("Dataset dtype should be set")
            .to_descriptor()
            .unwrap();
        match typedesc {
            hdf5_metno::types::TypeDescriptor::Unsigned(IntSize::U1) => {
                let ds_reader = ds.as_byte_reader()?;
                state.segment_state.segumented = SegmentType::NoSegment;
                let ds_buffered = BufReader::new(ds_reader);
                state
                    .img_state
                    .tx_load_imgfs
                    .send((ds_buffered, img_format))
                    .expect("Failed to send image load request");
            }
            hdf5_metno::types::TypeDescriptor::VarLenArray(arr_type) => {
                if matches!(
                    *arr_type,
                    hdf5_metno::types::TypeDescriptor::Unsigned(IntSize::U1)
                ) {
                    let i = state.img_state.idx_to_load;
                    state.img_state.idx_loaded = i;
                    state.segment_state.segumented = SegmentType::Image;
                    state.segment_state.segment_count = ds.shape()[0] as i32;
                    state.segment_state.idx = i;
                    state
                        .img_state
                        .tx_load_imgfsvlen
                        .send((ds.clone(), i, img_format))
                        .expect("Failed to send image load request");
                }
            }
            _ => {
                state.img_state.error = Some("Unsupported image format".to_string());
                let error_msg =
                    format!("Unsupported image format for dataset: {}", dsattr.display_name);
                f.render_widget(error_msg, inner_area);
                return Ok(());
            }
        }
    }

    Ok(())
}

pub fn handle_image_resize(tx_events: Sender<AppEvent>) -> Sender<ResizeRequest> {
    let (tx_worker, rx_worker) = channel::<ResizeRequest>();

    thread::spawn(move || loop {
        if let Ok(request) = rx_worker.recv() {
            match request.resize_encode() {
                Ok(r) => tx_events
                    .send(AppEvent::ImageResized(ImageResizeResult::Success(r)))
                    .expect("Failed to send image redraw event"),
                Err(e) => tx_events
                    .send(AppEvent::ImageResized(ImageResizeResult::Error(
                        e.to_string(),
                    )))
                    .expect("Failed to send image redraw event"),
            }
        }
    });
    tx_worker
}

pub fn handle_imagefs_load(
    tx_events: Sender<AppEvent>,
    tx_worker: Sender<ResizeRequest>,
    picker: Picker,
) -> Sender<(BufReader<ByteReader>, ImageFormat)> {
    let (tx_load, rx_load) = channel::<(BufReader<ByteReader>, ImageFormat)>();

    thread::spawn(move || loop {
        if let Ok((mut ds_reader, mut img_format)) = rx_load.recv() {
            // We drain to the latest
            while let Ok(queued) = rx_load.try_recv() {
                ds_reader = queued.0;
                img_format = queued.1;
            }
            if let Ok(dyn_img) = image::load(ds_reader, img_format) {
                let stateful_protocol = picker.new_resize_protocol(dyn_img);
                let thread_protocol =
                    ThreadProtocol::new(tx_worker.clone(), Some(stateful_protocol));
                tx_events
                    .send(AppEvent::ImageLoad(ImageLoadedResult::Success(
                        thread_protocol,
                    )))
                    .expect("Failed to send image loaded event");
            }
        }
    });
    tx_load
}

pub fn handle_imagefsvlen_load(
    tx_events: Sender<AppEvent>,
    tx_worker: Sender<ResizeRequest>,
    picker: Picker,
) -> Sender<(Dataset, i32, ImageFormat)> {
    let (tx_load, rx_load) = channel::<(Dataset, i32, ImageFormat)>();

    thread::spawn(move || loop {
        if let Ok((mut ds, mut idx, mut img_format)) = rx_load.recv() {
            // We drain to the latest
            while let Ok(queued) = rx_load.try_recv() {
                ds = queued.0;
                idx = queued.1;
                img_format = queued.2;
            }
            let data =
                match ds.read_slice_1d::<hdf5_metno::types::VarLenArray<u8>, _>(Selection::All) {
                    Ok(d) => d[idx as usize].as_slice().to_vec(),
                    Err(e) => {
                        tx_events
                            .send(AppEvent::ImageLoad(ImageLoadedResult::Failure(
                                e.to_string(),
                            )))
                            .expect("Failed to send image loaded event");
                        continue;
                    }
                };

            let cursor = std::io::Cursor::new(data);
            let data = BufReader::new(cursor);
            if let Ok(dyn_img) = image::load(data, img_format) {
                let stateful_protocol = picker.new_resize_protocol(dyn_img);
                let thread_protocol =
                    ThreadProtocol::new(tx_worker.clone(), Some(stateful_protocol));
                tx_events
                    .send(AppEvent::ImageLoad(ImageLoadedResult::Success(
                        thread_protocol,
                    )))
                    .expect("Failed to send image loaded event");
            }
        }
    });
    tx_load
}

pub enum ImageResizeResult {
    Success(ResizeResponse),
    Error(String),
}

pub enum ImageLoadedResult {
    Success(ThreadProtocol),
    Failure(String),
}

enum BitDepth {
    Bit8,
    Bit12,
    Unknown,
}

trait PixelBitDepth {
    fn bit_depth(&self) -> BitDepth;
}

impl PixelBitDepth for Dataset {
    fn bit_depth(&self) -> BitDepth {
        let dtype = self
            .dtype()
            .expect("Should get dtype from dataset")
            .to_descriptor()
            .unwrap();
        match dtype {
            hdf5_metno::types::TypeDescriptor::Unsigned(IntSize::U1) => BitDepth::Bit8,
            hdf5_metno::types::TypeDescriptor::Unsigned(IntSize::U2) => BitDepth::Bit12,
            _ => BitDepth::Unknown,
        }
    }
}

/// Build a Hyperslab selection that picks a 2D slice (h_dim, w_dim) from an N-D dataset.
/// All other dimensions are fixed at the values given in `indexes`.
fn build_image_selection(
    shape: &[usize],
    indexes: &[usize],
    h_dim: usize,
    w_dim: usize,
) -> Selection {
    let mut slice: Vec<SliceOrIndex> = Vec::new();
    for (dim, _) in shape.iter().enumerate() {
        if dim == h_dim || dim == w_dim {
            slice.push(SliceOrIndex::Unlimited {
                start: 0,
                step: 1,
                block: 1,
            });
        } else {
            slice.push(SliceOrIndex::Index(indexes[dim]));
        }
    }
    Selection::Hyperslab(Hyperslab::from(slice))
}

/// Build a Hyperslab selection that picks a 3D slice (h_dim, w_dim, channel_dim) for truecolor.
fn build_truecolor_selection(
    shape: &[usize],
    indexes: &[usize],
    h_dim: usize,
    w_dim: usize,
    channel_dim: usize,
) -> Selection {
    let mut slice: Vec<SliceOrIndex> = Vec::new();
    for (dim, _) in shape.iter().enumerate() {
        if dim == h_dim || dim == w_dim || dim == channel_dim {
            slice.push(SliceOrIndex::Unlimited {
                start: 0,
                step: 1,
                block: 1,
            });
        } else {
            slice.push(SliceOrIndex::Index(indexes[dim]));
        }
    }
    Selection::Hyperslab(Hyperslab::from(slice))
}

/// Window/level parameters for grayscale image contrast mapping.
#[derive(Debug, Clone)]
pub struct WindowLevel {
    pub center: f64,
    pub width: f64,
}

/// Message type for image load requests — uses file/dataset paths instead of HDF5 handles
/// to avoid HDF5 global lock contention with the main thread.
pub type ImageLoadRequest = (String, String, Vec<usize>, (usize, usize), ImageType, Option<WindowLevel>);

/// Max dataset size to cache in memory (256 MB)
const MAX_CACHE_BYTES: usize = 256 * 1024 * 1024;

/// Extract a 2D slice from an N-D array by fixing all dims except h_dim and w_dim.
/// Processes stepping dims from highest to lowest so axis indices stay stable.
fn extract_2d_slice<T: Clone + Default>(
    data: &ArrayD<T>,
    indexes: &[usize],
    h_dim: usize,
    w_dim: usize,
) -> Array2<T> {
    let ndim = data.ndim();
    let mut stepping: Vec<(usize, usize)> = (0..ndim)
        .filter(|&d| d != h_dim && d != w_dim)
        .map(|d| (d, indexes[d]))
        .collect();
    stepping.sort_by(|a, b| b.0.cmp(&a.0)); // highest first

    let mut arr = data.to_owned();
    for (dim, idx) in &stepping {
        arr = arr.index_axis(Axis(*dim), *idx).to_owned();
    }
    let arr2d = arr
        .into_dimensionality::<ndarray::Ix2>()
        .expect("slice should be 2D after removing stepping dims");
    // When h_dim > w_dim, after removing stepping dims axis 0 is W and
    // axis 1 is H (original dim order preserved). Transpose so axis 0 = H.
    if h_dim > w_dim {
        arr2d.t().to_owned()
    } else {
        arr2d
    }
}

enum CachedData {
    U8(ArrayD<u8>),
    U16(ArrayD<u16>),
}

pub fn handle_image_load(
    tx_events: Sender<AppEvent>,
    tx_worker: Sender<ResizeRequest>,
    picker: Picker,
    preload_cache: SharedCache,
) -> Sender<ImageLoadRequest> {
    let (tx_load, rx_load) = channel::<ImageLoadRequest>();
    thread::spawn(move || {
        // Worker-local dataset cache: holds the full N-D array in memory
        let mut cache_path: Option<String> = None;
        let mut cache_data: Option<CachedData> = None;

        loop {
        if let Ok((mut filename, mut ds_path, mut indexes, mut img_dims, mut img_format, mut window_level)) =
            rx_load.recv()
        {
            while let Ok(queued) = rx_load.try_recv() {
                filename = queued.0;
                ds_path = queued.1;
                indexes = queued.2;
                img_dims = queued.3;
                img_format = queued.4;
                window_level = queued.5;
            }

            let (h_dim, w_dim) = img_dims;

            // Check shared preload cache first
            if cache_path.as_deref() != Some(&ds_path) {
                let mut found_in_preload = false;
                if let Ok(guard) = preload_cache.lock() {
                    match guard.get(&ds_path) {
                        Some(CachedDataset::ImageU8(arr)) => {
                            cache_data = Some(CachedData::U8(arr.clone()));
                            cache_path = Some(ds_path.clone());
                            found_in_preload = true;
                        }
                        Some(CachedDataset::ImageU16(arr)) => {
                            cache_data = Some(CachedData::U16(arr.clone()));
                            cache_path = Some(ds_path.clone());
                            found_in_preload = true;
                        }
                        _ => {}
                    }
                }

                // Fall back to local cache logic if not in preload cache
                if !found_in_preload {
                cache_data = None;
                cache_path = None;

                let ds = match hdf5_metno::File::open(&filename)
                    .and_then(|f| f.dataset(&ds_path))
                {
                    Ok(ds) => ds,
                    Err(e) => {
                        tx_events
                            .send(AppEvent::ImageLoad(ImageLoadedResult::Failure(
                                format!("Failed to open dataset: {}", e),
                            )))
                            .expect("send");
                        continue;
                    }
                };

                let shape = ds.shape();
                let elem_size = ds.dtype().map(|d| d.size()).unwrap_or(1);
                let total_bytes: usize = shape.iter().product::<usize>() * elem_size;

                if total_bytes <= MAX_CACHE_BYTES {
                    let bit_depth = ds.bit_depth();
                    match bit_depth {
                        BitDepth::Bit8 => {
                            if let Ok(arr) = ds.read_dyn::<u8>() {
                                cache_data = Some(CachedData::U8(arr));
                                cache_path = Some(ds_path.clone());
                            }
                        }
                        BitDepth::Bit12 => {
                            if let Ok(arr) = ds.read_dyn::<u16>() {
                                cache_data = Some(CachedData::U16(arr));
                                cache_path = Some(ds_path.clone());
                            }
                        }
                        BitDepth::Unknown => {}
                    }
                }
                // If too large or caching failed, cache_data stays None → per-slice reads below
                }
            }

            // Build the image from cache or fallback to per-slice HDF5 read
            let dyn_img = match img_format {
                ImageType::Grayscale => {
                    match &cache_data {
                        Some(CachedData::U8(arr)) => {
                            if arr.ndim() < 2 {
                                send_failure(&tx_events, "Need at least 2D for Grayscale");
                                continue;
                            }
                            let slice = extract_2d_slice(arr, &indexes, h_dim, w_dim);
                            gray_u8_to_image(&slice)
                        }
                        Some(CachedData::U16(arr)) => {
                            if arr.ndim() < 2 {
                                send_failure(&tx_events, "Need at least 2D for Grayscale");
                                continue;
                            }
                            let slice = extract_2d_slice(arr, &indexes, h_dim, w_dim);
                            let slice = match &window_level {
                                Some(wl) => slice.mapv(|x| apply_window(x, wl.center, wl.width)),
                                None => {
                                    let clamped = slice.mapv(|x| if x > 4095 { 4095 } else { x });
                                    clamped.mapv(|x| ((x as f32 / 4095.0) * 255.0) as u8)
                                }
                            };
                            gray_u8_to_image(&slice)
                        }
                        None => {
                            // Fallback: per-slice read (large dataset or cache miss)
                            match read_grayscale_slice(&filename, &ds_path, &indexes, h_dim, w_dim) {
                                Ok(img) => img,
                                Err(e) => { send_failure(&tx_events, &e); continue; }
                            }
                        }
                    }
                }
                ImageType::Truecolor(ref interlace) => {
                    match &cache_data {
                        Some(CachedData::U8(arr)) => {
                            let ndim = arr.ndim();
                            let shape = arr.shape();
                            if ndim < 3 {
                                send_failure(&tx_events, "Need at least 3D for Truecolor");
                                continue;
                            }
                            let channel_dim = (0..ndim)
                                .find(|&d| d != h_dim && d != w_dim && (shape[d] == 3 || shape[d] == 4))
                                .unwrap_or(if matches!(interlace, InterlaceMode::Pixel) { ndim - 1 } else { 0 });

                            // Extract 3D slice: keep h_dim, w_dim, channel_dim
                            let mut stepping: Vec<(usize, usize)> = (0..ndim)
                                .filter(|&d| d != h_dim && d != w_dim && d != channel_dim)
                                .map(|d| (d, indexes[d]))
                                .collect();
                            stepping.sort_by(|a, b| b.0.cmp(&a.0));
                            let mut sub = arr.clone();
                            for (dim, idx) in &stepping {
                                sub = sub.index_axis(Axis(*dim), *idx).to_owned();
                            }
                            let data: Array3<u8> = sub
                                .into_dimensionality::<ndarray::Ix3>()
                                .expect("should be 3D");
                            // Swap H and W axes when h_dim > w_dim so that
                            // axis 0 = H, axis 1 = W (Pixel interlace) or
                            // axis 1 = H, axis 2 = W (Plane interlace).
                            let data = if h_dim > w_dim {
                                match interlace {
                                    InterlaceMode::Pixel => data.permuted_axes([1, 0, 2]).to_owned(),
                                    InterlaceMode::Plane => data.permuted_axes([0, 2, 1]).to_owned(),
                                }
                            } else {
                                data
                            };
                            truecolor_to_image(&data, interlace)
                        }
                        _ => {
                            // Fallback: per-slice read
                            match read_truecolor_slice(&filename, &ds_path, &indexes, h_dim, w_dim, &img_format) {
                                Ok(img) => img,
                                Err(e) => { send_failure(&tx_events, &e); continue; }
                            }
                        }
                    }
                }
                ImageType::Bitmap => {
                    // Bitmap: no caching (usually small 2D)
                    match read_bitmap_slice(&filename, &ds_path) {
                        Ok(img) => img,
                        Err(e) => { send_failure(&tx_events, &e); continue; }
                    }
                }
                _ => {
                    send_failure(&tx_events, "Unsupported image format");
                    continue;
                }
            };

            let stateful_protocol = picker.new_resize_protocol(dyn_img);
            let thread_protocol = ThreadProtocol::new(tx_worker.clone(), Some(stateful_protocol));
            tx_events
                .send(AppEvent::ImageLoad(ImageLoadedResult::Success(thread_protocol)))
                .expect("send");
        }
        }
    });
    tx_load
}

fn send_failure(tx: &Sender<AppEvent>, msg: &str) {
    tx.send(AppEvent::ImageLoad(ImageLoadedResult::Failure(msg.to_string())))
        .expect("send");
}

/// Create a multi-image load worker that tags responses with a slot index.
/// Returns a sender to submit load requests for this slot.
pub fn handle_multi_image_load(
    slot: usize,
    tx_events: Sender<AppEvent>,
    tx_worker: Sender<ResizeRequest>,
    picker: Picker,
    preload_cache: SharedCache,
) -> Sender<ImageLoadRequest> {
    let (tx_load, rx_load) = channel::<ImageLoadRequest>();
    thread::spawn(move || {
        let mut cache_path: Option<String> = None;
        let mut cache_data: Option<CachedData> = None;
        loop {
            if let Ok((mut filename, mut ds_path, mut indexes, mut img_dims, mut img_format, mut window_level)) =
                rx_load.recv()
            {
                while let Ok(queued) = rx_load.try_recv() {
                    filename = queued.0;
                    ds_path = queued.1;
                    indexes = queued.2;
                    img_dims = queued.3;
                    img_format = queued.4;
                    window_level = queued.5;
                }
                let (h_dim, w_dim) = img_dims;

                // Check caches
                if cache_path.as_deref() != Some(&ds_path) {
                    let mut found_in_preload = false;
                    if let Ok(guard) = preload_cache.lock() {
                        match guard.get(&ds_path) {
                            Some(CachedDataset::ImageU8(arr)) => {
                                cache_data = Some(CachedData::U8(arr.clone()));
                                cache_path = Some(ds_path.clone());
                                found_in_preload = true;
                            }
                            Some(CachedDataset::ImageU16(arr)) => {
                                cache_data = Some(CachedData::U16(arr.clone()));
                                cache_path = Some(ds_path.clone());
                                found_in_preload = true;
                            }
                            _ => {}
                        }
                    }
                    if !found_in_preload {
                        cache_data = None;
                        cache_path = None;
                        let ds = match hdf5_metno::File::open(&filename)
                            .and_then(|f| f.dataset(&ds_path))
                        {
                            Ok(ds) => ds,
                            Err(e) => {
                                tx_events
                                    .send(AppEvent::MultiImageLoad(slot, ImageLoadedResult::Failure(
                                        format!("Failed to open dataset: {}", e),
                                    )))
                                    .expect("send");
                                continue;
                            }
                        };
                        let shape = ds.shape();
                        let elem_size = ds.dtype().map(|d| d.size()).unwrap_or(1);
                        let total_bytes: usize = shape.iter().product::<usize>() * elem_size;
                        if total_bytes <= MAX_CACHE_BYTES {
                            match ds.bit_depth() {
                                BitDepth::Bit8 => {
                                    if let Ok(arr) = ds.read_dyn::<u8>() {
                                        cache_data = Some(CachedData::U8(arr));
                                        cache_path = Some(ds_path.clone());
                                    }
                                }
                                BitDepth::Bit12 => {
                                    if let Ok(arr) = ds.read_dyn::<u16>() {
                                        cache_data = Some(CachedData::U16(arr));
                                        cache_path = Some(ds_path.clone());
                                    }
                                }
                                BitDepth::Unknown => {}
                            }
                        }
                    }
                }

                let dyn_img = match img_format {
                    ImageType::Grayscale => match &cache_data {
                        Some(CachedData::U8(arr)) => {
                            if arr.ndim() < 2 { continue; }
                            let slice = extract_2d_slice(arr, &indexes, h_dim, w_dim);
                            gray_u8_to_image(&slice)
                        }
                        Some(CachedData::U16(arr)) => {
                            if arr.ndim() < 2 { continue; }
                            let slice = extract_2d_slice(arr, &indexes, h_dim, w_dim);
                            let slice = match &window_level {
                                Some(wl) => slice.mapv(|x| apply_window(x, wl.center, wl.width)),
                                None => {
                                    let clamped = slice.mapv(|x| if x > 4095 { 4095 } else { x });
                                    clamped.mapv(|x| ((x as f32 / 4095.0) * 255.0) as u8)
                                }
                            };
                            gray_u8_to_image(&slice)
                        }
                        None => continue,
                    },
                    _ => continue, // v1: only grayscale siblings
                };

                let stateful_protocol = picker.new_resize_protocol(dyn_img);
                let thread_protocol = ThreadProtocol::new(tx_worker.clone(), Some(stateful_protocol));
                tx_events
                    .send(AppEvent::MultiImageLoad(slot, ImageLoadedResult::Success(thread_protocol)))
                    .expect("send");
            }
        }
    });
    tx_load
}

/// Render a vertical grayscale colorbar with top/bottom labels.
fn render_colorbar(
    f: &mut Frame,
    area: &Rect,
    state: &AppState,
) {
    use ratatui::style::Color;
    use ratatui::text::{Line, Span};

    let h = area.height as usize;
    if h < 3 {
        return;
    }

    // Get window params or defaults
    let (wl_lo, wl_hi) = match (state.window_center, state.window_width) {
        (Some(c), Some(w)) if !state.auto_window => (c - w / 2.0, c + w / 2.0),
        _ => (0.0, 4095.0),
    };

    // Top label
    let top_label = format!("{:.0}", wl_hi);
    let top_line = Line::from(Span::styled(
        top_label,
        ratatui::style::Style::default().fg(Color::White),
    ));
    f.render_widget(
        top_line,
        Rect { x: area.x, y: area.y, width: area.width, height: 1 },
    );

    // Gradient bars
    for row in 1..h.saturating_sub(1) {
        let frac = 1.0 - (row as f64 / (h.saturating_sub(2)) as f64);
        let gray = (frac * 255.0) as u8;
        let bar = Line::from(Span::styled(
            "█".repeat(area.width as usize),
            ratatui::style::Style::default().fg(Color::Rgb(gray, gray, gray)),
        ));
        f.render_widget(
            bar,
            Rect { x: area.x, y: area.y + row as u16, width: area.width, height: 1 },
        );
    }

    // Bottom label
    let bot_label = format!("{:.0}", wl_lo);
    let bot_line = Line::from(Span::styled(
        bot_label,
        ratatui::style::Style::default().fg(Color::White),
    ));
    if h >= 2 {
        f.render_widget(
            bot_line,
            Rect { x: area.x, y: area.y + (h - 1) as u16, width: area.width, height: 1 },
        );
    }
}

/// Apply window/level mapping: maps a raw u16 value to u8 [0..255].
fn apply_window(raw: u16, center: f64, width: f64) -> u8 {
    let lo = center - width / 2.0;
    let hi = center + width / 2.0;
    let normalized = ((raw as f64 - lo) / (hi - lo)).clamp(0.0, 1.0);
    (normalized * 255.0) as u8
}

fn gray_u8_to_image(data: &Array2<u8>) -> image::DynamicImage {
    let (rows, cols) = (data.shape()[0], data.shape()[1]);
    let mut buf = image::GrayImage::new(cols as u32, rows as u32);
    for j in 0..rows {
        for i in 0..cols {
            buf.put_pixel(i as u32, j as u32, image::Luma([data[[j, i]]]));
        }
    }
    image::DynamicImage::ImageLuma8(buf)
}

fn truecolor_to_image(data: &Array3<u8>, interlace: &InterlaceMode) -> image::DynamicImage {
    let shape = data.shape();
    match interlace {
        InterlaceMode::Pixel => {
            let mut buf = image::RgbaImage::new(shape[1] as u32, shape[0] as u32);
            for i in 0..shape[1] {
                for j in 0..shape[0] {
                    buf.put_pixel(i as u32, j as u32, image::Rgba([
                        data[[j, i, 0]], data[[j, i, 1]], data[[j, i, 2]], 255,
                    ]));
                }
            }
            image::DynamicImage::ImageRgba8(buf)
        }
        InterlaceMode::Plane => {
            let mut buf = image::RgbaImage::new(shape[2] as u32, shape[1] as u32);
            for i in 0..shape[2] {
                for j in 0..shape[1] {
                    buf.put_pixel(i as u32, j as u32, image::Rgba([
                        data[[0, j, i]], data[[1, j, i]], data[[2, j, i]], 255,
                    ]));
                }
            }
            image::DynamicImage::ImageRgba8(buf)
        }
    }
}

/// Fallback: read a single 2D grayscale slice from HDF5 (for datasets > 256 MB)
fn read_grayscale_slice(
    filename: &str, ds_path: &str, indexes: &[usize], h_dim: usize, w_dim: usize,
) -> std::result::Result<image::DynamicImage, String> {
    let ds = hdf5_metno::File::open(filename)
        .and_then(|f| f.dataset(ds_path))
        .map_err(|e| format!("Failed to open: {}", e))?;
    let shape = ds.shape();
    if shape.len() < 2 { return Err("Need at least 2D".into()); }
    let selection = build_image_selection(&shape, indexes, h_dim, w_dim);
    match ds.bit_depth() {
        BitDepth::Bit8 => {
            let data: Array2<u8> = ds.read_slice(selection).map_err(|e| e.to_string())?;
            let data = if h_dim > w_dim { data.t().to_owned() } else { data };
            Ok(gray_u8_to_image(&data))
        }
        BitDepth::Bit12 => {
            let data: Array2<u16> = ds.read_slice(selection).map_err(|e| e.to_string())?;
            let data = if h_dim > w_dim { data.t().to_owned() } else { data };
            let data = data.mapv(|x| if x > 4095 { 4095 } else { x });
            let data = data.mapv(|x| ((x as f32 / 4095.0) * 255.0) as u8);
            Ok(gray_u8_to_image(&data))
        }
        BitDepth::Unknown => Err("Unsupported bit depth".into()),
    }
}

/// Fallback: read a single 3D truecolor slice from HDF5
fn read_truecolor_slice(
    filename: &str, ds_path: &str, indexes: &[usize],
    h_dim: usize, w_dim: usize, img_type: &ImageType,
) -> std::result::Result<image::DynamicImage, String> {
    let ds = hdf5_metno::File::open(filename)
        .and_then(|f| f.dataset(ds_path))
        .map_err(|e| format!("Failed to open: {}", e))?;
    let shape = ds.shape();
    let ndim = shape.len();
    let interlace = match img_type {
        ImageType::Truecolor(m) => m,
        _ => return Err("Not truecolor".into()),
    };
    if ndim < 3 { return Err("Need at least 3D for Truecolor".into()); }
    let data: Array3<u8> = if ndim == 3 {
        ds.read_slice(Selection::All).map_err(|e| e.to_string())?
    } else {
        let channel_dim = (0..ndim)
            .find(|&d| d != h_dim && d != w_dim && (shape[d] == 3 || shape[d] == 4))
            .unwrap_or(if matches!(interlace, InterlaceMode::Pixel) { ndim - 1 } else { 0 });
        let sel = build_truecolor_selection(&shape, indexes, h_dim, w_dim, channel_dim);
        ds.read_slice(sel).map_err(|e| e.to_string())?
    };
    let data = if h_dim > w_dim {
        match interlace {
            InterlaceMode::Pixel => data.permuted_axes([1, 0, 2]).to_owned(),
            InterlaceMode::Plane => data.permuted_axes([0, 2, 1]).to_owned(),
        }
    } else {
        data
    };
    Ok(truecolor_to_image(&data, interlace))
}

/// Fallback: read a bitmap dataset
fn read_bitmap_slice(filename: &str, ds_path: &str) -> std::result::Result<image::DynamicImage, String> {
    let ds = hdf5_metno::File::open(filename)
        .and_then(|f| f.dataset(ds_path))
        .map_err(|e| format!("Failed to open: {}", e))?;
    let shape = ds.shape();
    let data: Array2<bool> = ds.read_slice(s![.., ..]).map_err(|e| e.to_string())?;
    let mut buf = image::GrayImage::new(shape[0] as u32, shape[1] as u32);
    for i in 0..shape[1] {
        for j in 0..shape[0] {
            let pixel = if data[[i, j]] { image::Luma([255]) } else { image::Luma([0]) };
            buf.put_pixel(i as u32, j as u32, pixel);
        }
    }
    Ok(image::DynamicImage::ImageLuma8(buf))
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::{Array2, Array3, ArrayD, IxDyn};

    // ── extract_2d_slice tests ─────────────────────────────────────

    #[test]
    fn extract_2d_no_transpose() {
        let arr = ArrayD::from_shape_fn(IxDyn(&[3, 4]), |idx| (idx[0] * 4 + idx[1]) as u8);
        let slice = extract_2d_slice(&arr, &[0, 0], 0, 1);
        assert_eq!(slice.shape(), &[3, 4]);
        assert_eq!(slice[[0, 0]], 0);
        assert_eq!(slice[[2, 3]], 11);
    }

    #[test]
    fn extract_2d_transpose() {
        let arr = ArrayD::from_shape_fn(IxDyn(&[3, 4]), |idx| (idx[0] * 4 + idx[1]) as u8);
        let slice = extract_2d_slice(&arr, &[0, 0], 1, 0);
        assert_eq!(slice.shape(), &[4, 3]);
        // Transposed: slice[j,i] == arr[i,j]
        assert_eq!(slice[[0, 0]], 0);
        assert_eq!(slice[[3, 2]], 11);
    }

    #[test]
    fn extract_3d_slice() {
        let arr = ArrayD::from_shape_fn(IxDyn(&[5, 10, 20]), |idx| {
            (idx[0] * 200 + idx[1] * 20 + idx[2]) as u16
        });
        let slice = extract_2d_slice(&arr, &[2, 0, 0], 1, 2);
        assert_eq!(slice.shape(), &[10, 20]);
        // slice[r,c] should be arr[2, r, c]
        assert_eq!(slice[[0, 0]], 2 * 200);
        assert_eq!(slice[[9, 19]], 2 * 200 + 9 * 20 + 19);
    }

    #[test]
    fn extract_3d_transposed() {
        let arr = ArrayD::from_shape_fn(IxDyn(&[5, 10, 20]), |idx| {
            (idx[0] * 200 + idx[1] * 20 + idx[2]) as u16
        });
        let slice = extract_2d_slice(&arr, &[2, 0, 0], 2, 1);
        assert_eq!(slice.shape(), &[20, 10]);
        // Transposed: slice[c,r] == arr[2, r, c]
        assert_eq!(slice[[0, 0]], 2 * 200);
        assert_eq!(slice[[19, 9]], 2 * 200 + 9 * 20 + 19);
    }

    #[test]
    fn extract_4d_slice() {
        let arr = ArrayD::from_shape_fn(IxDyn(&[2, 3, 4, 5]), |idx| {
            (idx[0] * 60 + idx[1] * 20 + idx[2] * 5 + idx[3]) as u16
        });
        // Fix dims 0 and 2, keep h_dim=1, w_dim=3
        let slice = extract_2d_slice(&arr, &[1, 0, 2, 0], 1, 3);
        assert_eq!(slice.shape(), &[3, 5]);
        // slice[r,c] == arr[1, r, 2, c]
        assert_eq!(slice[[0, 0]], 1 * 60 + 0 * 20 + 2 * 5 + 0);
        assert_eq!(slice[[2, 4]], 1 * 60 + 2 * 20 + 2 * 5 + 4);
    }

    #[test]
    fn extract_4d_transposed() {
        let arr = ArrayD::from_shape_fn(IxDyn(&[2, 3, 4, 5]), |idx| {
            (idx[0] * 60 + idx[1] * 20 + idx[2] * 5 + idx[3]) as u16
        });
        let slice = extract_2d_slice(&arr, &[1, 0, 2, 0], 3, 1);
        assert_eq!(slice.shape(), &[5, 3]);
        // Transposed: slice[c,r] == arr[1, r, 2, c]
        assert_eq!(slice[[0, 0]], 1 * 60 + 0 * 20 + 2 * 5 + 0);
        assert_eq!(slice[[4, 2]], 1 * 60 + 2 * 20 + 2 * 5 + 4);
    }

    #[test]
    fn extract_pixel_values() {
        let arr = ArrayD::from_shape_fn(IxDyn(&[3, 4, 5]), |idx| {
            (idx[0] * 20 + idx[1] * 5 + idx[2]) as u16
        });
        let slice = extract_2d_slice(&arr, &[1, 0, 0], 1, 2);
        // Verify every pixel
        for r in 0..4 {
            for c in 0..5 {
                assert_eq!(slice[[r, c]], (1 * 20 + r * 5 + c) as u16);
            }
        }
    }

    #[test]
    fn extract_hw_swap_is_transpose() {
        let arr = ArrayD::from_shape_fn(IxDyn(&[10, 20]), |idx| (idx[0] * 20 + idx[1]) as u8);
        let a = extract_2d_slice(&arr, &[0, 0], 0, 1);
        let b = extract_2d_slice(&arr, &[0, 0], 1, 0);
        for i in 0..10 {
            for j in 0..20 {
                assert_eq!(a[[i, j]], b[[j, i]]);
            }
        }
    }

    // ── Image conversion tests ─────────────────────────────────────

    #[test]
    fn gray_u8_dims() {
        let data = Array2::from_shape_fn((3, 4), |_| 128u8);
        let img = gray_u8_to_image(&data);
        assert_eq!(img.width(), 4);
        assert_eq!(img.height(), 3);
    }

    #[test]
    fn gray_u8_pixels() {
        let data = Array2::from_shape_vec((2, 2), vec![10u8, 20, 30, 40]).unwrap();
        let img = gray_u8_to_image(&data);
        let buf = img.to_luma8();
        assert_eq!(buf.get_pixel(0, 0).0[0], 10);
        assert_eq!(buf.get_pixel(1, 0).0[0], 20);
        assert_eq!(buf.get_pixel(0, 1).0[0], 30);
        assert_eq!(buf.get_pixel(1, 1).0[0], 40);
    }

    #[test]
    fn truecolor_pixel_interlace() {
        use crate::h5f::InterlaceMode;
        // shape [H=2, W=3, C=3] in Pixel mode
        let data = Array3::from_shape_fn((2, 3, 3), |(h, w, c)| {
            (h * 9 + w * 3 + c) as u8
        });
        let img = truecolor_to_image(&data, &InterlaceMode::Pixel);
        assert_eq!(img.width(), 3);
        assert_eq!(img.height(), 2);
        let rgba = img.to_rgba8();
        let px = rgba.get_pixel(0, 0);
        assert_eq!(px.0, [0, 1, 2, 255]);
    }

    #[test]
    fn truecolor_plane_interlace() {
        use crate::h5f::InterlaceMode;
        // shape [C=3, H=2, W=3] in Plane mode
        let data = Array3::from_shape_fn((3, 2, 3), |(c, h, w)| {
            (c * 6 + h * 3 + w) as u8
        });
        let img = truecolor_to_image(&data, &InterlaceMode::Plane);
        assert_eq!(img.width(), 3);
        assert_eq!(img.height(), 2);
        let rgba = img.to_rgba8();
        // pixel (0,0): R=data[0,0,0]=0, G=data[1,0,0]=6, B=data[2,0,0]=12, A=255
        let px = rgba.get_pixel(0, 0);
        assert_eq!(px.0, [0, 6, 12, 255]);
    }

    #[test]
    fn gray_u8_single_pixel() {
        let data = Array2::from_shape_vec((1, 1), vec![128u8]).unwrap();
        let img = gray_u8_to_image(&data);
        let buf = img.to_luma8();
        assert_eq!(buf.get_pixel(0, 0).0[0], 128);
    }

    // ── Window/Level tests ───────────────────────────────────────

    #[test]
    fn window_full_range() {
        // Full range [0, 4095] → should map 0→0, 4095→255
        assert_eq!(apply_window(0, 2047.5, 4095.0), 0);
        assert_eq!(apply_window(4095, 2047.5, 4095.0), 255);
    }

    #[test]
    fn window_narrow() {
        // Narrow window centered at 2000, width 100 → [1950, 2050]
        assert_eq!(apply_window(1950, 2000.0, 100.0), 0);
        assert_eq!(apply_window(2050, 2000.0, 100.0), 255);
        // Midpoint should be ~128
        let mid = apply_window(2000, 2000.0, 100.0);
        assert!((mid as i16 - 127).abs() <= 1);
    }

    #[test]
    fn window_clamp() {
        // Values outside window should clamp to 0 or 255
        assert_eq!(apply_window(0, 2000.0, 100.0), 0);
        assert_eq!(apply_window(4095, 2000.0, 100.0), 255);
    }
}
