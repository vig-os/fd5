use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc::channel;
use std::sync::{Arc, Mutex};

use arboard::Clipboard;
use ratatui_image::picker::Picker;

use crate::config::Config;
use crate::h5f::{H5F, Node};
use crate::ui::command::{Command, CommandState};
use crate::ui::mchart::MultiChartState;
use crate::ui::preload::PreloadCache;
use crate::ui::state::*;

static TEST_COUNTER: AtomicUsize = AtomicUsize::new(0);

/// Create a minimal AppState with a dataset of the given shape.
/// Returns None if HDF5 file creation or clipboard init fails.
pub fn make_test_state(shape: &[usize]) -> Option<AppState<'static>> {
    let id = TEST_COUNTER.fetch_add(1, Ordering::Relaxed);
    let tmp_path = std::env::temp_dir().join(format!(
        "h5v_test_dims_{}d_{}.h5",
        shape.len(),
        id
    ));

    // Create temp HDF5 file with a dataset of the given shape
    {
        let file = hdf5_metno::File::create(&tmp_path).ok()?;
        file.new_dataset::<u8>()
            .shape(shape)
            .create("test_ds")
            .ok()?;
    }

    let h5f = H5F::open(tmp_path.to_str()?.to_string()).ok()?;

    let (tx_imgfs, _rx1) = channel();
    let (tx_imgfsvlen, _rx2) = channel();
    let (tx_img, _rx3) = channel();
    #[allow(deprecated)]
    let picker = Picker::from_fontsize((7, 14));

    let mut state = AppState {
        root: h5f.root.clone(),
        multi_chart: MultiChartState::new(picker.clone()),
        segment_state: SegmentState {
            idx: 0,
            segment_count: 0,
            segumented: SegmentType::NoSegment,
        },
        command_state: CommandState {
            command_buffer: String::new(),
            last_command: Command::Noop,
            cursor: 0,
        },
        treeview: vec![],
        tree_view_cursor: 0,
        attributes_view_cursor: AttributeCursor {
            attribute_index: 0,
            attribute_offset: 0,
            attribute_view_selection: AttributeViewSelection::Name,
        },
        focus: Focus::Content,
        clipboard: Clipboard::new().ok()?,
        mode: Mode::Normal,
        copying: false,
        searcher: None,
        show_tree_view: true,
        content_mode: ContentShowMode::Preview,
        img_state: ImgState {
            protocol: None,
            tx_load_imgfs: tx_imgfs,
            tx_load_imgfsvlen: tx_imgfsvlen,
            tx_load_img: tx_img,
            ds: None,
            idx_to_load: 0,
            idx_loaded: -1,
            indexes_to_load: vec![],
            indexes_loaded: vec![],
            img_dims_loaded: (0, 1),
            error: None,
            picker,
            tx_events: None,
            tx_resize: None,
        },
        matrix_view_state: MatrixViewState {
            col_offset: 0,
            row_offset: 0,
            rows_currently_available: 0,
            cols_currently_available: 0,
        },
        preload_cache: Arc::new(Mutex::new(PreloadCache::new(0))),
        nav_accel: NavAccel::new(),
        settings_state: SettingsState::from_config(&Config::default()),
        cfg: Config::default(),
        chart_log_y: false,
        chart_log_x: false,
        chart_mode: ChartMode::Line,
        window_center: None,
        window_width: None,
        auto_window: true,
        multi_image_mode: false,
        multi_image_siblings: vec![],
        fd5_status: None,
        fd5_file_path: None,
    };

    state.compute_tree_view();

    // Find the dataset in the treeview and set cursor to it
    for (i, item) in state.treeview.iter().enumerate() {
        let node = item.node.borrow();
        if matches!(&node.node, Node::Dataset(_, _)) {
            drop(node);
            state.tree_view_cursor = i;
            break;
        }
    }

    // Don't delete tmp file — AppState holds HDF5 dataset handles
    Some(state)
}

/// Create an AppState with multiple grayscale image datasets under the same group.
/// Creates /images/img_0, /images/img_1, etc. with CLASS=IMAGE, IMAGE_SUBCLASS=IMAGE_GRAYSCALE.
/// The cursor is set to the first image dataset.
/// Returns None if HDF5 file creation or clipboard init fails.
pub fn make_multi_image_state(count: usize, shape: &[usize]) -> Option<AppState<'static>> {
    let id = TEST_COUNTER.fetch_add(1, Ordering::Relaxed);
    let tmp_path = std::env::temp_dir().join(format!("h5v_test_multi_img_{}.h5", id));

    {
        let file = hdf5_metno::File::create(&tmp_path).ok()?;
        let grp = file.create_group("images").ok()?;
        for i in 0..count {
            let name = format!("img_{}", i);
            let ds = grp
                .new_dataset::<u8>()
                .shape(shape)
                .create(name.as_str())
                .ok()?;
            let class_val = unsafe {
                hdf5_metno::types::VarLenUnicode::from_str_unchecked("IMAGE")
            };
            ds.new_attr::<hdf5_metno::types::VarLenUnicode>()
                .create("CLASS")
                .ok()?
                .write_scalar(&class_val)
                .ok()?;
            let subclass_val = unsafe {
                hdf5_metno::types::VarLenUnicode::from_str_unchecked("IMAGE_GRAYSCALE")
            };
            ds.new_attr::<hdf5_metno::types::VarLenUnicode>()
                .create("IMAGE_SUBCLASS")
                .ok()?
                .write_scalar(&subclass_val)
                .ok()?;
        }
    }

    let h5f = H5F::open(tmp_path.to_str()?.to_string()).ok()?;

    let (tx_imgfs, _rx1) = channel();
    let (tx_imgfsvlen, _rx2) = channel();
    let (tx_img, _rx3) = channel();
    #[allow(deprecated)]
    let picker = Picker::from_fontsize((7, 14));

    let mut state = AppState {
        root: h5f.root.clone(),
        multi_chart: MultiChartState::new(picker.clone()),
        segment_state: SegmentState {
            idx: 0,
            segment_count: 0,
            segumented: SegmentType::NoSegment,
        },
        command_state: CommandState {
            command_buffer: String::new(),
            last_command: Command::Noop,
            cursor: 0,
        },
        treeview: vec![],
        tree_view_cursor: 0,
        attributes_view_cursor: AttributeCursor {
            attribute_index: 0,
            attribute_offset: 0,
            attribute_view_selection: AttributeViewSelection::Name,
        },
        focus: Focus::Content,
        clipboard: Clipboard::new().ok()?,
        mode: Mode::Normal,
        copying: false,
        searcher: None,
        show_tree_view: true,
        content_mode: ContentShowMode::Preview,
        img_state: ImgState {
            protocol: None,
            tx_load_imgfs: tx_imgfs,
            tx_load_imgfsvlen: tx_imgfsvlen,
            tx_load_img: tx_img,
            ds: None,
            idx_to_load: 0,
            idx_loaded: -1,
            indexes_to_load: vec![],
            indexes_loaded: vec![],
            img_dims_loaded: (0, 1),
            error: None,
            picker,
            tx_events: None,
            tx_resize: None,
        },
        matrix_view_state: MatrixViewState {
            col_offset: 0,
            row_offset: 0,
            rows_currently_available: 0,
            cols_currently_available: 0,
        },
        preload_cache: Arc::new(Mutex::new(PreloadCache::new(0))),
        nav_accel: NavAccel::new(),
        settings_state: SettingsState::from_config(&Config::default()),
        cfg: Config::default(),
        chart_log_y: false,
        chart_log_x: false,
        chart_mode: ChartMode::Line,
        window_center: None,
        window_width: None,
        auto_window: true,
        multi_image_mode: false,
        multi_image_siblings: vec![],
        fd5_status: None,
        fd5_file_path: None,
    };

    // Expand all groups so datasets are visible in treeview
    {
        let root = state.root.borrow();
        for child in &root.children {
            let mut child_node = child.borrow_mut();
            if matches!(&child_node.node, Node::Group(_, _)) {
                let _ = child_node.expand_toggle();
            }
        }
    }

    state.compute_tree_view();

    // Set cursor to the first image dataset
    for (i, item) in state.treeview.iter().enumerate() {
        let node = item.node.borrow();
        if matches!(&node.node, Node::Dataset(_, _)) {
            drop(node);
            state.tree_view_cursor = i;
            break;
        }
    }

    Some(state)
}
