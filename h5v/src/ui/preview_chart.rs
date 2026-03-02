use image::{DynamicImage, ImageBuffer, Rgb};
use plotters::{
    chart::ChartBuilder,
    prelude::{BitMapBackend, IntoDrawingArea},
    style::{Color as _, IntoFont},
};

use ratatui::{
    layout::{Constraint, Layout, Rect},
    style::Style,
    symbols::Marker,
    text::Span,
    widgets::{Axis, Chart, Dataset, GraphType},
    Frame,
};
use ratatui_image::StatefulImage;

use crate::{
    color_consts,
    data::{DatasetPlottingData, PreviewSelection, Previewable, SliceSelection},
    error::AppError,
    h5f::{H5FNode, Node},
    ui::{
        dims::render_dim_selector,
        preload::CachedDataset,
        preview::render_string_preview,
        segment_scroll::render_segment_scroll,
        state::{ChartMode, SegmentType},
        std_comp_render::{render_error, render_string, render_unsupported_rendering},
    },
    utils::image_capable_terminal,
};

use super::state::AppState;

/// Build DatasetPlottingData from a cached 1-D f64 vec using the same PreviewSelection logic.
fn plot_from_cached(raw: &[f64], selection: &PreviewSelection, shape: &[usize]) -> Option<DatasetPlottingData> {
    // For multi-dim datasets the cache holds the full flat array; we need the 1-D slice
    // along the x-axis with other dims fixed by index.
    // Compute strides to extract the 1-D line from the flat array.
    let ndim = shape.len();
    if ndim == 0 {
        return None;
    }

    // Compute row-major strides
    let mut strides = vec![1usize; ndim];
    for i in (0..ndim - 1).rev() {
        strides[i] = strides[i + 1] * shape[i + 1];
    }

    // Base offset from fixed indexes (all dims except x)
    let mut base_offset: usize = 0;
    for dim in 0..ndim {
        if dim != selection.x {
            let idx = if dim < selection.index.len() { selection.index[dim] } else { 0 };
            base_offset += idx * strides[dim];
        }
    }

    let x_len = shape[selection.x];
    let (start, end) = match &selection.slice {
        SliceSelection::All => (0, x_len),
        SliceSelection::FromTo(a, b) => (*a, *b),
    };

    let stride_x = strides[selection.x];
    let data: Vec<(f64, f64)> = (start..end)
        .enumerate()
        .map(|(i, xi)| {
            let flat_idx = base_offset + xi * stride_x;
            let y = if flat_idx < raw.len() { raw[flat_idx] } else { f64::NAN };
            (i as f64, y)
        })
        .collect();

    let length = data.len();
    let max = data.iter().map(|(_, y)| *y).fold(f64::NAN, f64::max);
    let min = data.iter().map(|(_, y)| *y).fold(f64::NAN, f64::min);

    Some(DatasetPlottingData { data, length, max, min })
}

pub fn render_chart_preview(
    f: &mut Frame,
    area: &Rect,
    node: &mut H5FNode,
    state: &mut AppState,
) -> Result<(), AppError> {
    let (ds, ds_full_path) = match &node.node {
        Node::Dataset(ds, attr) => (ds.clone(), attr.full_path.clone()),
        _ => return Ok(()),
    };
    let ds_meta = match &node.node {
        Node::Dataset(_, attr) => attr,
        _ => return Ok(()),
    };

    let shape = ds.shape();
    let total_dims = shape.len();
    let x_selectable_dims: Vec<usize> = shape
        .iter()
        .enumerate()
        .filter(|(_, v)| **v > 1)
        .map(|(i, _)| i)
        .collect();

    if x_selectable_dims.is_empty() {
        match ds_meta.matrixable {
            Some(t) => match t {
                crate::sprint_typedesc::MatrixRenderType::Float64 => {
                    let ds = ds.read_scalar::<f64>();
                    let ds = match ds {
                        Ok(ds) => ds,
                        Err(e) => {
                            render_error(f, area, format!("Error reading scalar: {}", e));
                            return Ok(());
                        }
                    };
                    render_string(f, area, node, ds, None);
                }
                crate::sprint_typedesc::MatrixRenderType::Uint64 => {
                    let ds = ds.read_scalar::<u64>();
                    let ds = match ds {
                        Ok(ds) => ds,
                        Err(e) => {
                            render_error(f, area, format!("Error reading scalar: {}", e));
                            return Ok(());
                        }
                    };
                    render_string(f, area, node, ds, None);
                }
                crate::sprint_typedesc::MatrixRenderType::Int64 => {
                    let ds = ds.read_scalar::<i64>();
                    let ds = match ds {
                        Ok(ds) => ds,
                        Err(e) => {
                            render_error(f, area, format!("Error reading scalar: {}", e));
                            return Ok(());
                        }
                    };
                    render_string(f, area, node, ds, None);
                }
                crate::sprint_typedesc::MatrixRenderType::Compound => {
                    render_unsupported_rendering(
                        f,
                        area,
                        &node.node,
                        "Compound types are not supported for chart preview",
                    );
                    return Ok(());
                }
                crate::sprint_typedesc::MatrixRenderType::Strings => {
                    render_string_preview(f, area, node)?;
                    return Ok(());
                }
            },
            None => {
                render_unsupported_rendering(
                    f,
                    area,
                    &node.node,
                    "Not enough data for selectable dimensions for x-axis",
                );
            }
        }
        return Ok(());
    }

    let selected_indexe_length = node.selected_indexes.len();
    for i in 0..selected_indexe_length {
        if !x_selectable_dims.contains(&i) {
            node.selected_indexes[i] = 0;
        }
    }

    if !x_selectable_dims.contains(&node.selected_x) {
        node.selected_x = x_selectable_dims[0];
    }
    if node.selected_dim == node.selected_x {
        node.selected_dim = x_selectable_dims
            .iter()
            .find(|&&x| x != node.selected_x)
            .cloned()
            .unwrap_or(0);
    }

    let chart_area = if x_selectable_dims.len() > 1 {
        let areas_split =
            Layout::vertical(vec![Constraint::Length(4), Constraint::Min(1)]).split(*area);
        render_dim_selector(f, &areas_split[0], node, &shape, false)?;
        areas_split[1].inner(ratatui::layout::Margin {
            horizontal: 0,
            vertical: 1,
        })
    } else {
        area.inner(ratatui::layout::Margin {
            horizontal: 0,
            vertical: 1,
        })
    };

    // Try to get cached chart data from preload cache
    let cached_raw: Option<Vec<f64>> = state
        .preload_cache
        .lock()
        .ok()
        .and_then(|guard| match guard.get(&ds_full_path) {
            Some(CachedDataset::ChartF64(v)) => Some(v.clone()),
            _ => None,
        });

    let max_segment_size = state.cfg.ui.chart_segment_size;
    let (chart_area, data_preview) = if shape[node.selected_x] > max_segment_size {
        state.segment_state.segumented = SegmentType::Chart;
        state.segment_state.segment_count =
            (shape[node.selected_x] as f64 / max_segment_size as f64).ceil() as i32;
        let areas_split =
            Layout::horizontal(vec![Constraint::Min(1), Constraint::Length(2)]).split(*area);
        render_segment_scroll(f, &areas_split[1], state)?;

        let max_len = shape[node.selected_x];
        let selection = PreviewSelection {
            x: node.selected_x,
            index: node.selected_indexes[0..total_dims].to_vec(),
            slice: SliceSelection::FromTo(
                max_segment_size * state.segment_state.idx as usize,
                (max_segment_size * (state.segment_state.idx + 1) as usize).min(max_len),
            ),
        };
        let data_preview = match &cached_raw {
            Some(raw) => plot_from_cached(raw, &selection, &shape)
                .unwrap_or_else(|| ds.plot(selection).unwrap()),
            None => ds.plot(selection)?,
        };
        (areas_split[0], data_preview)
    } else {
        let selection = PreviewSelection {
            x: node.selected_x,
            index: node.selected_indexes[0..total_dims].to_vec(),
            slice: SliceSelection::All,
        };
        let data_preview = match &cached_raw {
            Some(raw) => plot_from_cached(raw, &selection, &shape)
                .unwrap_or_else(|| ds.plot(selection).unwrap()),
            None => ds.plot(selection)?,
        };
        (chart_area, data_preview)
    };

    if image_capable_terminal() {
        let (x, y) = state.img_state.picker.font_size();
        let height = chart_area.height as u32 * y as u32;
        let width = chart_area.width as u32 * x as u32;
        let mut buffer = vec![0; (height * width * 3) as usize];
        let x_min = if state.segment_state.idx > 0 {
            max_segment_size as f64 * state.segment_state.idx as f64
        } else {
            0.0
        };
        if data_preview.min.is_nan()
            || data_preview.max.is_nan()
            || data_preview.min.is_infinite()
            || data_preview.min >= data_preview.max
        {
            render_error(
                f,
                &chart_area,
                "Data not valid, could not establish min and max bounds for chart\nIt seems the data only contains NaN or infinite values.",
            );
        } else if state.chart_mode == ChartMode::Histogram {
            render_image_histogram(&mut buffer, width, height, &data_preview)?;
        } else {
            render_image_chart(&mut buffer, width, height, x_min, data_preview, state.chart_log_x, state.chart_log_y)?;
            let image = ImageBuffer::<Rgb<u8>, _>::from_raw(width, height, buffer)
                .expect("buffer size mismatch");
            let image_widget = StatefulImage::default();
            let dyn_img = DynamicImage::ImageRgb8(image);
            let mut stateful_protocol = state.img_state.picker.new_resize_protocol(dyn_img);
            f.render_stateful_widget(image_widget, chart_area, &mut stateful_protocol);
        }
    } else {
        let x_label_count = match chart_area.width {
            0 => 0,
            _ => chart_area.width / 8,
        };
        let x_labels = (0..=x_label_count)
            .map(|i| {
                let x = (data_preview.length as f64) * (i as f64) / (x_label_count as f64);
                Span::styled(format!("{:.1}", x), color_consts::COLOR_WHITE)
            })
            .collect::<Vec<_>>();

        let y_label_count = match chart_area.height {
            0 => 0,
            _ => chart_area.height / 4,
        };

        let y_labels = (0..=y_label_count)
            .map(|i| {
                let y = data_preview.min
                    + (data_preview.max - data_preview.min) * (i as f64) / (y_label_count as f64);
                Span::styled(format!("{:.1}", y), color_consts::COLOR_WHITE)
            })
            .collect::<Vec<_>>();

        // into a &'a [(f64, f64)]
        let data: &[(f64, f64)] = &data_preview.data;
        let ds = Dataset::default()
            .marker(Marker::Braille)
            .graph_type(GraphType::Line)
            .data(data);
        let bg = match (&state.focus, &state.mode) {
            (super::state::Focus::Content, super::state::Mode::Normal) => {
                color_consts::FOCUS_BG_COLOR
            }
            _ => color_consts::BG_COLOR,
        };
        let chart = Chart::new(vec![ds])
            .style(Style::default().bg(bg))
            .x_axis(
                Axis::default()
                    .title("X axis")
                    .style(Style::default().fg(ratatui::style::Color::White))
                    .labels(x_labels)
                    .bounds((0.0, data_preview.length as f64).into()),
            )
            .y_axis(
                Axis::default()
                    .title("Y axis")
                    .style(Style::default().fg(ratatui::style::Color::White))
                    .labels(y_labels)
                    .bounds((data_preview.min, data_preview.max).into()),
            );
        f.render_widget(chart, chart_area);
    }

    Ok(())
}

fn render_image_chart(
    buffer: &mut [u8],
    width: u32,
    height: u32,
    x_min: f64,
    data_preview: DatasetPlottingData,
    log_x: bool,
    log_y: bool,
) -> Result<(), AppError> {
    let root = BitMapBackend::with_buffer(buffer, (width, height)).into_drawing_area();
    root.margin(10, 10, 10, 10);
    root.fill(&plotters::prelude::WHITE).unwrap();
    let max = data_preview.max;
    let y_label_area_size = format!("{max:.4}").len() as u32 * 3 + 30;

    let x_end = x_min + data_preview.length as f64;
    let (plot_x_min, plot_x_max) = if log_x {
        (x_min.max(1.0).log10(), x_end.max(1.0).log10())
    } else {
        (x_min, x_end)
    };
    let (plot_y_min, plot_y_max) = if log_y {
        (
            data_preview.min.max(f64::EPSILON).log10(),
            data_preview.max.max(f64::EPSILON).log10(),
        )
    } else {
        (data_preview.min, data_preview.max)
    };

    let mut chart = ChartBuilder::on(&root)
        .margin(10)
        .x_label_area_size(30)
        .y_label_area_size(y_label_area_size)
        .build_cartesian_2d(plot_x_min..plot_x_max, plot_y_min..plot_y_max)
        .unwrap();

    {
        let mut mesh = chart.configure_mesh();
        mesh.x_label_style(("sans-serif", 18).into_font())
            .y_label_style(("sans-serif", 18).into_font());
        if log_y {
            mesh.y_label_formatter(&|v| format!("{:.1e}", 10.0_f64.powf(*v)));
        }
        if log_x {
            mesh.x_label_formatter(&|v| format!("{:.1e}", 10.0_f64.powf(*v)));
        }
        mesh.draw().unwrap();
    }

    let data: Vec<(f64, f64)> = data_preview
        .data
        .iter()
        .map(|(x, y)| {
            let px = if log_x { (x_min + *x).max(1.0).log10() } else { x_min + *x };
            let py = if log_y { y.max(f64::EPSILON).log10() } else { *y };
            (px, py)
        })
        .collect();
    let line_series = plotters::prelude::LineSeries::new(data, plotters::prelude::BLUE);
    chart.draw_series(line_series).unwrap();
    root.present().unwrap();
    Ok(())
}

/// Compute histogram bins from (x, y) data (uses y values).
/// Returns (bin_center, count) pairs.
pub fn compute_histogram(data: &[(f64, f64)], num_bins: usize) -> Vec<(f64, f64)> {
    if data.is_empty() || num_bins == 0 {
        return vec![];
    }
    let values: Vec<f64> = data.iter().map(|(_, y)| *y).filter(|y| y.is_finite()).collect();
    if values.is_empty() {
        return vec![];
    }
    let min = values.iter().copied().fold(f64::INFINITY, f64::min);
    let max = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if (max - min).abs() < f64::EPSILON {
        return vec![(min, values.len() as f64)];
    }
    let bin_width = (max - min) / num_bins as f64;
    let mut counts = vec![0u32; num_bins];
    for &v in &values {
        let idx = ((v - min) / bin_width) as usize;
        let idx = idx.min(num_bins - 1);
        counts[idx] += 1;
    }
    counts
        .iter()
        .enumerate()
        .map(|(i, &c)| {
            let center = min + (i as f64 + 0.5) * bin_width;
            (center, c as f64)
        })
        .collect()
}

fn render_image_histogram(
    buffer: &mut [u8],
    width: u32,
    height: u32,
    data_preview: &DatasetPlottingData,
) -> Result<(), AppError> {
    let num_bins = 64.min(data_preview.data.len().max(1));
    let hist_data = compute_histogram(&data_preview.data, num_bins);
    if hist_data.is_empty() {
        return Ok(());
    }
    let y_max = hist_data.iter().map(|(_, c)| *c).fold(0.0_f64, f64::max);
    let x_min = hist_data.first().map(|(x, _)| *x).unwrap_or(0.0);
    let x_max = hist_data.last().map(|(x, _)| *x).unwrap_or(1.0);
    let bar_width = if hist_data.len() > 1 {
        (hist_data[1].0 - hist_data[0].0) * 0.9
    } else {
        1.0
    };

    let root = BitMapBackend::with_buffer(buffer, (width, height)).into_drawing_area();
    root.fill(&plotters::prelude::WHITE).unwrap();

    let mut chart = ChartBuilder::on(&root)
        .margin(10)
        .x_label_area_size(30)
        .y_label_area_size(50)
        .build_cartesian_2d(x_min - bar_width..x_max + bar_width, 0.0..y_max * 1.1)
        .unwrap();

    chart
        .configure_mesh()
        .x_label_style(("sans-serif", 18).into_font())
        .y_label_style(("sans-serif", 18).into_font())
        .draw()
        .unwrap();

    let bars = hist_data.iter().map(|(center, count)| {
        let x0 = center - bar_width / 2.0;
        let x1 = center + bar_width / 2.0;
        plotters::prelude::Rectangle::new(
            [(x0, 0.0), (x1, *count)],
            plotters::prelude::BLUE.filled(),
        )
    });
    chart.draw_series(bars).unwrap();
    root.present().unwrap();
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn histogram_uniform_data() {
        let data: Vec<(f64, f64)> = (0..100).map(|i| (i as f64, i as f64)).collect();
        let hist = compute_histogram(&data, 10);
        assert_eq!(hist.len(), 10);
        let total: f64 = hist.iter().map(|(_, c)| c).sum();
        assert_eq!(total as usize, 100);
    }

    #[test]
    fn histogram_single_value() {
        let data = vec![(0.0, 5.0), (1.0, 5.0), (2.0, 5.0)];
        let hist = compute_histogram(&data, 10);
        assert_eq!(hist.len(), 1);
        assert_eq!(hist[0].1 as usize, 3);
    }

    #[test]
    fn histogram_empty_data() {
        let hist = compute_histogram(&[], 10);
        assert!(hist.is_empty());
    }
}
