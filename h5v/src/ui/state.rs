use std::{cell::RefCell, io::BufReader, path::PathBuf, rc::Rc, sync::mpsc::Sender, time::Instant};

use arboard::Clipboard;
use hdf5_metno::{ByteReader, Dataset, Hyperslab, Selection, SliceOrIndex};
use image::ImageFormat;
use ratatui::crossterm::event::KeyCode;
use ratatui_image::{picker::Picker, thread::ThreadProtocol};

use super::preload::SharedCache;

use crate::{
    config::{Config, ConfigValue, FieldMeta, NavigationConfig},
    error::AppError,
    h5f::{H5FNode, Node},
    search::Searcher,
    ui::mchart::MultiChartState,
};

use super::{
    command::{Command, CommandState},
    input::EventResult,
    tree_view::TreeItem,
};

#[derive(Debug, Clone)]
pub enum LastFocused {
    Attributes,
    Content,
}

#[derive(Debug, Clone)]
pub enum Focus {
    Tree(LastFocused),
    Attributes,
    Content,
}

#[derive(Debug, Clone)]
pub enum Mode {
    Normal,
    Search,
    Help,
    Command,
    MultiChart,
    Settings,
}

#[derive(Debug, Clone, PartialEq, Copy)]
pub enum ContentShowMode {
    Preview,
    Matrix,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ChartMode {
    Line,
    Histogram,
}

pub struct ImgState {
    pub protocol: Option<ThreadProtocol>,
    pub tx_load_imgfs: Sender<(BufReader<ByteReader>, ImageFormat)>,
    pub tx_load_imgfsvlen: Sender<(Dataset, i32, ImageFormat)>,
    pub tx_load_img: Sender<super::image_preview::ImageLoadRequest>,
    pub ds: Option<String>,
    pub error: Option<String>,
    pub idx_to_load: i32,
    pub idx_loaded: i32,
    pub indexes_to_load: Vec<usize>,
    pub indexes_loaded: Vec<usize>,
    pub img_dims_loaded: (usize, usize),
    pub picker: Picker,
    pub tx_events: Option<std::sync::mpsc::Sender<super::app::AppEvent>>,
    pub tx_resize: Option<Sender<ratatui_image::thread::ResizeRequest>>,
}

impl ImgState {}

pub enum AttributeViewSelection {
    Name,
    Value,
}

pub struct AttributeCursor {
    pub attribute_index: usize,
    pub attribute_view_selection: AttributeViewSelection,
    pub attribute_offset: usize,
}

pub struct MatrixViewState {
    pub col_offset: usize,
    pub row_offset: usize,
    pub rows_currently_available: usize,
    pub cols_currently_available: usize,
}

pub enum SegmentType {
    Image,
    Chart,
    NoSegment,
}

pub struct SegmentState {
    pub idx: i32,
    pub segumented: SegmentType,
    pub segment_count: i32,
}

pub struct SettingsState {
    pub fields: Vec<(FieldMeta, ConfigValue)>,
    pub cursor: usize,
    pub editing: bool,
    pub edit_buffer: String,
    pub edit_cursor: usize,
    pub message: Option<String>,
}

impl SettingsState {
    pub fn from_config(cfg: &Config) -> Self {
        Self {
            fields: cfg.field_metas(),
            cursor: 0,
            editing: false,
            edit_buffer: String::new(),
            edit_cursor: 0,
            message: None,
        }
    }

    pub fn refresh(&mut self, cfg: &Config) {
        self.fields = cfg.field_metas();
    }
}

pub struct NavAccel {
    last_key: Option<KeyCode>,
    last_press: Instant,
    tap_count: u32,
    hold_start: Instant,
    hold_origin: usize,
    hold_direction: isize,
    holding: bool,
    // Config values (copied from NavigationConfig to avoid lifetime issues)
    tap_window_ms: u128,
    hold_traverse_secs: f64,
    double_tap_fraction: f64,
    min_hold_velocity: f64,
    max_hold_velocity_steps: f64,
    max_hold_velocity_pct: f64,
}

impl NavAccel {
    pub fn from_config(nav: &NavigationConfig) -> Self {
        Self {
            last_key: None,
            last_press: Instant::now(),
            tap_count: 0,
            hold_start: Instant::now(),
            hold_origin: 0,
            hold_direction: 1,
            holding: false,
            tap_window_ms: nav.tap_window_ms as u128,
            hold_traverse_secs: nav.hold_traverse_secs,
            double_tap_fraction: nav.double_tap_fraction,
            min_hold_velocity: nav.min_hold_velocity,
            max_hold_velocity_steps: nav.max_hold_velocity_steps,
            max_hold_velocity_pct: nav.max_hold_velocity_pct,
        }
    }

    pub fn new() -> Self {
        Self::from_config(&NavigationConfig::default())
    }

    pub fn update_from_config(&mut self, nav: &NavigationConfig) {
        self.tap_window_ms = nav.tap_window_ms as u128;
        self.hold_traverse_secs = nav.hold_traverse_secs;
        self.double_tap_fraction = nav.double_tap_fraction;
        self.min_hold_velocity = nav.min_hold_velocity;
        self.max_hold_velocity_steps = nav.max_hold_velocity_steps;
        self.max_hold_velocity_pct = nav.max_hold_velocity_pct;
    }

    /// Press event. Quick taps without holds between them trigger multi-tap:
    /// - single tap → step 1
    /// - double tap → ~5% jump (configured by `double_tap_fraction`)
    /// - triple tap → home/end (returns dim_size, clamped by caller)
    ///
    /// Holds (Repeat events) reset tap_count, so press-hold-release-press
    /// never triggers multi-tap — only genuine quick taps do.
    pub fn on_press(&mut self, key: KeyCode, dim_size: usize) -> usize {
        let now = Instant::now();
        let gap = now.duration_since(self.last_press).as_millis();

        if self.last_key == Some(key) && gap < self.tap_window_ms && self.tap_count > 0 {
            self.tap_count += 1;
        } else {
            self.tap_count = 1;
        }

        let step = match self.tap_count {
            2 => ((dim_size as f64 * self.double_tap_fraction) as usize).max(2),
            n if n >= 3 => dim_size,
            _ => 1,
        };

        self.last_key = Some(key);
        self.last_press = now;
        self.hold_start = now;
        self.holding = false;

        step
    }

    /// Hold (key repeat). Returns the **absolute target position** based on
    /// elapsed time, direction, and the position when the hold started.
    ///
    /// Uses a quadratic acceleration curve with a linear velocity floor so
    /// small dimensions still feel responsive. Because each frame independently
    /// computes the target from the clock, there is no accumulation drift —
    /// the numbers advance smoothly regardless of frame rate.
    pub fn on_repeat(&mut self, origin: usize, direction: isize, dim_size: usize) -> usize {
        if !self.holding {
            self.holding = true;
            self.hold_origin = origin;
            self.hold_direction = direction;
        }
        self.tap_count = 0; // holds invalidate multi-tap

        let elapsed = self.hold_start.elapsed().as_secs_f64();
        Self::hold_target(
            elapsed,
            self.hold_origin,
            self.hold_direction,
            dim_size,
            self.hold_traverse_secs,
            self.min_hold_velocity,
            self.max_hold_velocity_steps,
            self.max_hold_velocity_pct,
        )
    }

    /// Pure computation: absolute target position for a hold at `elapsed_secs`.
    /// Quadratic acceleration with a linear velocity floor for responsiveness.
    /// Pure computation: absolute target position for a hold at `elapsed_secs`.
    ///
    /// Velocity ramps linearly from `min_vel` to `max_vel` over `traverse_secs`.
    /// Displacement is the integral: `min*t + (max-min)*t²/(2*traverse)`.
    /// This gives smooth acceleration governed by a single time constant.
    fn hold_target(
        elapsed_secs: f64,
        origin: usize,
        direction: isize,
        dim_size: usize,
        traverse_secs: f64,
        min_vel: f64,
        max_vel_steps: f64,
        max_vel_pct: f64,
    ) -> usize {
        // Effective max: larger of absolute steps cap and percentage cap
        let max_vel = max_vel_steps.max(dim_size as f64 * max_vel_pct);
        let t = elapsed_secs.min(traverse_secs);
        let over = elapsed_secs - t; // time spent at max velocity after ramp

        // Velocity ramps linearly: v(t) = min + (max - min) * t / traverse
        // Displacement = integral = min*t + (max-min)*t²/(2*traverse)
        let ramp_disp = min_vel * t + (max_vel - min_vel) * t * t / (2.0 * traverse_secs);
        // After ramp completes, continue at max velocity
        let total_disp = ramp_disp + max_vel * over;
        let displacement = total_disp as usize;

        // Return absolute target position
        if direction > 0 {
            (origin + displacement).min(dim_size.saturating_sub(1))
        } else {
            origin.saturating_sub(displacement)
        }
    }

    /// Release event. Returns true if user was holding (had repeat events).
    pub fn on_release(&mut self) -> bool {
        let was = self.holding;
        self.holding = false;
        was
    }
}

pub struct AppState<'a> {
    pub root: Rc<RefCell<H5FNode>>,
    pub treeview: Vec<TreeItem<'a>>,
    pub tree_view_cursor: usize,
    pub clipboard: Clipboard,
    pub copying: bool,
    pub attributes_view_cursor: AttributeCursor,
    pub focus: Focus,
    pub multi_chart: MultiChartState,
    pub mode: Mode,
    pub searcher: Option<Searcher>,
    pub show_tree_view: bool,
    pub content_mode: ContentShowMode,
    pub img_state: ImgState,
    pub matrix_view_state: MatrixViewState,
    pub segment_state: SegmentState,
    pub command_state: CommandState,
    pub preload_cache: SharedCache,
    pub nav_accel: NavAccel,
    pub settings_state: SettingsState,
    pub cfg: Config,
    pub chart_log_y: bool,
    pub chart_log_x: bool,
    pub chart_mode: ChartMode,
    pub window_center: Option<f64>,
    pub window_width: Option<f64>,
    pub auto_window: bool,
    pub multi_image_mode: bool,
    pub multi_image_siblings: Vec<MultiImageSlot>,
    pub fd5_status: Option<fd5::Fd5Status>,
    pub fd5_file_path: Option<PathBuf>,
}

/// State for a single sibling image in multi-image mode.
pub struct MultiImageSlot {
    pub ds_path: String,
    pub filename: String,
    pub img_type: crate::h5f::ImageType,
    pub protocol: Option<ThreadProtocol>,
    pub loaded_indexes: Vec<usize>,
    pub tx_load: Option<std::sync::mpsc::Sender<super::image_preview::ImageLoadRequest>>,
}

type Result<T> = std::result::Result<T, AppError>;
impl AppState<'_> {
    pub fn swap_content_show_mode(&mut self, available: Vec<ContentShowMode>) {
        if available.is_empty() {
            return;
        }
        match self.content_mode {
            ContentShowMode::Preview if available.contains(&ContentShowMode::Matrix) => {
                self.content_mode = ContentShowMode::Matrix;
            }
            _ => {
                self.content_mode = ContentShowMode::Preview;
            }
        }
    }

    pub fn content_show_mode_eval(&self, available: Vec<ContentShowMode>) -> ContentShowMode {
        if available.contains(&self.content_mode) {
            self.content_mode
        } else {
            available[0]
        }
    }

    pub fn change_row(&mut self, delta: isize) -> Result<EventResult> {
        match self.content_mode {
            ContentShowMode::Matrix => {
                let current_node = &self.treeview[self.tree_view_cursor];
                let mut current_node = current_node.node.borrow_mut();
                if let Node::Dataset(_, dsattr) = &current_node.node {
                    let shape = dsattr.shape.clone();
                    let new_selected_row = ((current_node.selected_row as isize + delta)
                        % shape.len() as isize) as usize
                        % shape.len();
                    if new_selected_row != current_node.selected_col {
                        current_node.selected_row = new_selected_row;
                        return Ok(EventResult::Redraw);
                    }
                    current_node.selected_row = ((current_node.selected_row as isize + delta + 1)
                        % shape.len() as isize)
                        as usize
                        % shape.len();

                    Ok(EventResult::Redraw)
                } else {
                    Ok(EventResult::Continue)
                }
            }
            _ => Ok(EventResult::Continue),
        }
    }

    pub fn get_1d_selection(&self) -> Option<(Dataset, Selection)> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let node = current_node.node.borrow();
        let Node::Dataset(ds, dsattr) = &node.node else {
            return None;
        };
        let selected_dim = node.selected_x;
        let mut slice: Vec<SliceOrIndex> = Vec::new();
        for (dim, _) in dsattr.shape.iter().enumerate() {
            if dim == selected_dim {
                slice.push(SliceOrIndex::Unlimited {
                    start: 0,
                    step: 1,
                    block: 1,
                });
            } else {
                slice.push(SliceOrIndex::Index(node.selected_indexes[dim]));
            }
        }
        let hyperslap = Hyperslab::from(slice);
        Some((ds.clone(), Selection::Hyperslab(hyperslap)))
    }

    pub fn change_selected_dimension(&mut self, delta: isize) -> Result<EventResult> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let mut node = current_node.node.borrow_mut();
        let Node::Dataset(_, dsattr) = &node.node else {
            return Ok(EventResult::Continue);
        };
        let current_shape_len = dsattr.shape.len() as isize;
        let next = node.selected_dim as isize + delta;
        let new_selected_dim = if next < 0 {
            (current_shape_len - 1) as usize
        } else if next >= current_shape_len {
            0_usize
        } else {
            next as usize
        };
        match self.content_mode {
            ContentShowMode::Preview => {
                let is_image = dsattr.image.is_some();
                if is_image {
                    // For image mode, skip selected_row (H) and selected_col (W) dims
                    if new_selected_dim != node.selected_col
                        && new_selected_dim != node.selected_row
                    {
                        node.selected_dim = new_selected_dim;
                    } else {
                        let next_next = new_selected_dim as isize + delta;
                        let next_next = if next_next < 0 {
                            (current_shape_len - 1) as usize
                        } else if next_next >= current_shape_len {
                            0_usize
                        } else {
                            next_next as usize
                        };
                        if next_next != node.selected_col && next_next != node.selected_row {
                            node.selected_dim = next_next.clamp(0, current_shape_len as usize);
                        } else {
                            let next_next_next = next_next as isize + delta;
                            let next_next_next = if next_next_next < 0 {
                                (current_shape_len - 1) as usize
                            } else if next_next_next >= current_shape_len {
                                0_usize
                            } else {
                                next_next_next as usize
                            };
                            node.selected_dim =
                                next_next_next.clamp(0, current_shape_len as usize);
                        }
                    }
                } else if new_selected_dim != node.selected_x {
                    node.selected_dim = new_selected_dim;
                } else {
                    let next_next = new_selected_dim as isize + delta;
                    let next_next = if next_next < 0 {
                        (current_shape_len - 1) as usize
                    } else if next_next >= current_shape_len {
                        0_usize
                    } else {
                        next_next as usize
                    };
                    node.selected_dim = next_next.clamp(0, current_shape_len as usize);
                }
                Ok(EventResult::Redraw)
            }
            ContentShowMode::Matrix => {
                if new_selected_dim != node.selected_col && new_selected_dim != node.selected_row {
                    node.selected_dim = new_selected_dim;
                } else {
                    let next_next = new_selected_dim as isize + delta;
                    let next_next = if next_next < 0 {
                        (current_shape_len - 1) as usize
                    } else if next_next >= current_shape_len {
                        0_usize
                    } else {
                        next_next as usize
                    };
                    if next_next != node.selected_col && next_next != node.selected_row {
                        node.selected_dim = next_next.clamp(0, current_shape_len as usize);
                    } else {
                        let next_next_next = next_next as isize + delta;
                        let next_next_next = if next_next_next < 0 {
                            (current_shape_len - 1) as usize
                        } else if next_next_next >= current_shape_len {
                            0_usize
                        } else {
                            next_next_next as usize
                        };
                        node.selected_dim = next_next_next.clamp(0, current_shape_len as usize);
                    }
                }
                Ok(EventResult::Redraw)
            }
        }
    }

    pub fn change_selected_index(&mut self, delta: isize) -> Result<EventResult> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let mut node = current_node.node.borrow_mut();
        let Node::Dataset(_, dsattr) = &node.node else {
            return Ok(EventResult::Continue);
        };
        let ndim = dsattr.shape.len();
        let x_shape = dsattr.shape[node.selected_dim];
        let is_image = dsattr.image.is_some();
        let current_selected_dim = node.selected_indexes[node.selected_dim] as isize;
        let new_current_x_index =
            (current_selected_dim + delta).clamp(0, x_shape as isize - 1) as usize;
        let selected_x = node.selected_dim;
        node.selected_indexes[selected_x] = new_current_x_index;

        // Update indexes_to_load for image mode so is_from_ds() triggers reload
        if is_image && self.content_mode == ContentShowMode::Preview {
            self.img_state.indexes_to_load = node.selected_indexes[..ndim].to_vec();
        }

        Ok(EventResult::Redraw)
    }

    pub fn change_col(&mut self, delta: isize) -> Result<EventResult> {
        match self.content_mode {
            ContentShowMode::Matrix => {
                let current_node = &self.treeview[self.tree_view_cursor];
                let mut current_node = current_node.node.borrow_mut();
                if let Node::Dataset(_, dsattr) = &current_node.node {
                    let shape = dsattr.shape.clone();
                    let new_selected_col = ((current_node.selected_col as isize + delta)
                        % shape.len() as isize) as usize
                        % shape.len();
                    if new_selected_col != current_node.selected_row {
                        current_node.selected_col = new_selected_col;
                        return Ok(EventResult::Redraw);
                    }
                    current_node.selected_col = ((current_node.selected_col as isize + delta + 1)
                        % shape.len() as isize)
                        as usize
                        % shape.len();

                    Ok(EventResult::Redraw)
                } else {
                    Ok(EventResult::Continue)
                }
            }
            _ => Ok(EventResult::Continue),
        }
    }

    pub fn change_x(&mut self, delta: isize) -> Result<EventResult> {
        match self.content_mode {
            ContentShowMode::Preview => {
                let current_node = &self.treeview[self.tree_view_cursor];
                let mut current_node = current_node.node.borrow_mut();
                if let Node::Dataset(_, dsattr) = &current_node.node {
                    let shape = dsattr.shape.clone();
                    current_node.selected_x = ((current_node.selected_x as isize + delta)
                        % shape.len() as isize)
                        as usize
                        % shape.len();
                    Ok(EventResult::Redraw)
                } else {
                    Ok(EventResult::Continue)
                }
            }
            _ => Ok(EventResult::Continue),
        }
    }

    pub fn up(&mut self, dec: usize) -> Result<EventResult> {
        match self.content_mode {
            ContentShowMode::Preview => match self.segment_state.segumented {
                SegmentType::Image => Ok(EventResult::Continue),
                SegmentType::Chart => {
                    self.segment_state.idx = self
                        .segment_state
                        .idx
                        .saturating_sub(dec as i32)
                        .clamp(0, self.segment_state.segment_count - 1);
                    Ok(EventResult::Redraw)
                }
                SegmentType::NoSegment => {
                    self.img_state.idx_to_load = self.segment_state.idx;
                    let current_node = &self.treeview[self.tree_view_cursor];
                    let mut node = current_node.node.borrow_mut();
                    let new_offset = node.line_offset as isize - dec as isize;
                    let new_offset = if new_offset < 0 {
                        0
                    } else {
                        new_offset as usize
                    };
                    node.line_offset = new_offset;

                    Ok(EventResult::Redraw)
                }
            },
            ContentShowMode::Matrix => {
                let current_node = &self.treeview[self.tree_view_cursor];
                let node = &current_node.node.borrow_mut();
                let current_node = &node.node;
                if self.matrix_view_state.row_offset == 0 {
                    return Ok(EventResult::Redraw);
                }
                if let Node::Dataset(_, dsattr) = current_node {
                    let row_selected_shape = dsattr.shape[node.selected_row];
                    self.matrix_view_state.row_offset =
                        (self.matrix_view_state.row_offset.saturating_sub(dec)).min(
                            row_selected_shape
                                .saturating_sub(self.matrix_view_state.rows_currently_available),
                        );
                    Ok(EventResult::Redraw)
                } else {
                    Ok(EventResult::Redraw)
                }
            }
        }
    }

    pub fn down(&mut self, inc: usize) -> Result<EventResult> {
        match self.content_mode {
            ContentShowMode::Preview => match self.segment_state.segumented {
                SegmentType::Image => Ok(EventResult::Continue),
                SegmentType::Chart => {
                    self.segment_state.idx = self
                        .segment_state
                        .idx
                        .saturating_add(inc as i32)
                        .clamp(0, self.segment_state.segment_count - 1);
                    Ok(EventResult::Redraw)
                }
                SegmentType::NoSegment => {
                    self.img_state.idx_to_load = self.segment_state.idx;

                    self.img_state.idx_to_load = self.segment_state.idx;
                    let current_node = &self.treeview[self.tree_view_cursor];
                    let mut node = current_node.node.borrow_mut();
                    let new_offset = node.line_offset + inc;
                    node.line_offset = new_offset;
                    Ok(EventResult::Redraw)
                }
            },
            ContentShowMode::Matrix => {
                let node = &self.treeview[self.tree_view_cursor].node.borrow_mut();
                let current_node = &node.node;
                if let Node::Dataset(_, dsattr) = current_node {
                    let row_selected_shape = dsattr.shape[node.selected_row];
                    self.matrix_view_state.row_offset = (self.matrix_view_state.row_offset + inc)
                        .min(
                            row_selected_shape
                                .saturating_sub(self.matrix_view_state.rows_currently_available),
                        );
                    Ok(EventResult::Redraw)
                } else {
                    Ok(EventResult::Redraw)
                }
            }
        }
    }

    pub fn set(&mut self, idx: usize) -> Result<EventResult> {
        match self.content_mode {
            ContentShowMode::Preview => match self.segment_state.segumented {
                SegmentType::Image => Ok(EventResult::Continue),
                SegmentType::Chart => {
                    if idx > 0 {
                        self.segment_state.idx =
                            ((idx - 1) as i32).clamp(0, self.segment_state.segment_count - 1);
                        Ok(EventResult::Redraw)
                    } else {
                        self.segment_state.idx = 0;
                        Ok(EventResult::Redraw)
                    }
                }
                SegmentType::NoSegment => {
                    self.img_state.idx_to_load = idx as i32;
                    Ok(EventResult::Redraw)
                }
            },
            ContentShowMode::Matrix => {
                let node = &self.treeview[self.tree_view_cursor].node.borrow_mut();
                let current_node = &node.node;
                if let Node::Dataset(_, dsattr) = current_node {
                    let row_selected_shape = dsattr.shape[node.selected_row];
                    self.matrix_view_state.row_offset = idx.min(
                        row_selected_shape
                            .saturating_sub(self.matrix_view_state.rows_currently_available),
                    );
                    Ok(EventResult::Redraw)
                } else {
                    Ok(EventResult::Redraw)
                }
            }
        }
    }

    pub fn execute_command(&mut self, command: &Command) -> Result<EventResult> {
        match command {
            super::command::Command::Increment(increment) => self.down(*increment),
            super::command::Command::Decrement(decrement) => self.up(*decrement),
            super::command::Command::Seek(seek) => self.set(*seek),
            super::command::Command::Settings => {
                self.settings_state.refresh(&self.cfg);
                self.mode = Mode::Settings;
                Ok(EventResult::Redraw)
            }
            super::command::Command::Verify => {
                let Some(ref fp) = self.fd5_file_path else {
                    return Ok(EventResult::Error("No file path available".to_string()));
                };
                self.fd5_status = Some(fd5::Fd5Status::Checking);
                match fd5::verify(fp) {
                    Ok(status) => {
                        let msg = match &status {
                            fd5::Fd5Status::Valid(h) => format!("fd5 valid: {}", h),
                            fd5::Fd5Status::Invalid { stored, computed } => {
                                format!("fd5 INVALID: stored={}, computed={}", stored, computed)
                            }
                            fd5::Fd5Status::NotFd5 => "Not an fd5 file".to_string(),
                            fd5::Fd5Status::Error(e) => format!("fd5 error: {}", e),
                            fd5::Fd5Status::Checking => unreachable!(),
                        };
                        self.fd5_status = Some(status);
                        Ok(EventResult::Info(msg))
                    }
                    Err(e) => {
                        self.fd5_status = Some(fd5::Fd5Status::Error(format!("{}", e)));
                        Ok(EventResult::Error(format!("fd5 verify failed: {}", e)))
                    }
                }
            }
            super::command::Command::Edit {
                attr_name,
                value,
                in_place,
            } => {
                let Some(ref fp) = self.fd5_file_path else {
                    return Ok(EventResult::Error("No file path available".to_string()));
                };
                let mode = if *in_place {
                    fd5::edit::EditMode::InPlace
                } else {
                    fd5::edit::EditMode::CopyOnWrite
                };
                let plan = fd5::edit::EditPlan {
                    source_path: fp.clone(),
                    attr_path: "/".to_string(),
                    attr_name: attr_name.clone(),
                    old_value: String::new(),
                    new_value: fd5::edit::AttrValue::String(value.clone()),
                    mode,
                };
                match plan.apply() {
                    Ok(result) => {
                        let msg = format!(
                            "Edited '{}' on {}\nHash: {} -> {}",
                            attr_name,
                            result.output_path.display(),
                            result.old_content_hash,
                            result.new_content_hash,
                        );
                        Ok(EventResult::Info(msg))
                    }
                    Err(e) => Ok(EventResult::Error(format!("Edit failed: {}", e))),
                }
            }
            super::command::Command::Quit => Ok(EventResult::Quit),
            super::command::Command::Help => {
                self.mode = Mode::Help;
                Ok(EventResult::Redraw)
            }
            super::command::Command::Noop => Ok(EventResult::Redraw),
        }
    }

    pub fn reexecute_command(&mut self) -> Result<EventResult> {
        let last_command = &self.command_state.last_command.clone();
        self.execute_command(last_command)
    }

    pub fn right(&mut self, arg: isize) -> Result<EventResult> {
        match self.content_mode {
            ContentShowMode::Preview => match self.segment_state.segumented {
                SegmentType::Image => Ok(EventResult::Continue),
                SegmentType::Chart => Ok(EventResult::Continue),
                SegmentType::NoSegment => {
                    let current_node = &self.treeview[self.tree_view_cursor];
                    let mut node = current_node.node.borrow_mut();
                    let new_col_offset = node.col_offset.saturating_add(arg).max(0);
                    node.col_offset = new_col_offset;
                    Ok(EventResult::Redraw)
                }
            },
            ContentShowMode::Matrix => self.change_col(arg),
        }
    }

    pub fn image_move_dim(&mut self, delta: isize) -> Result<EventResult> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let mut node = current_node.node.borrow_mut();
        let Node::Dataset(_, dsattr) = &node.node else {
            return Ok(EventResult::Continue);
        };
        let ndim = dsattr.shape.len() as isize;
        let next = (node.selected_dim as isize + delta).rem_euclid(ndim) as usize;
        node.selected_dim = next;
        Ok(EventResult::Redraw)
    }

    /// Send an image load request to the worker thread for the current node's selection.
    /// Sends file path + dataset path (no HDF5 handles) to avoid global lock contention.
    pub fn send_image_load(&mut self) -> Result<EventResult> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let node = current_node.node.borrow();
        let Node::Dataset(_, dsattr) = &node.node else {
            return Ok(EventResult::Redraw);
        };
        let Some(ref img_type) = dsattr.image else {
            return Ok(EventResult::Redraw);
        };
        let ndim = dsattr.shape.len();
        let h_dim = node.selected_row;
        let w_dim = node.selected_col;
        let indexes: Vec<usize> = node.selected_indexes[..ndim].to_vec();

        self.img_state.indexes_to_load = indexes.clone();
        self.img_state.img_dims_loaded = (h_dim, w_dim);
        self.img_state.ds = Some(dsattr.full_path.clone());

        let wl = if !self.auto_window {
            self.window_center.zip(self.window_width).map(|(c, w)| {
                crate::ui::image_preview::WindowLevel { center: c, width: w }
            })
        } else {
            None
        };
        self.img_state.tx_load_img.send((
            dsattr.filename.clone(),
            dsattr.full_path.clone(),
            indexes.clone(),
            (h_dim, w_dim),
            img_type.clone(),
            wl.clone(),
        ))?;

        // Also trigger loads for multi-image siblings
        if self.multi_image_mode {
            for sibling in &self.multi_image_siblings {
                if let Some(ref tx) = sibling.tx_load {
                    let _ = tx.send((
                        sibling.filename.clone(),
                        sibling.ds_path.clone(),
                        indexes.clone(),
                        (h_dim, w_dim),
                        sibling.img_type.clone(),
                        wl.clone(),
                    ));
                }
            }
        }

        Ok(EventResult::Redraw)
    }

    #[cfg_attr(not(test), allow(dead_code))]
    pub fn image_change_index(&mut self, delta: isize) -> Result<EventResult> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let mut node = current_node.node.borrow_mut();
        let Node::Dataset(_, dsattr) = &node.node else {
            return Ok(EventResult::Continue);
        };
        let ndim = dsattr.shape.len();
        let selected = node.selected_dim;
        // No-op if selected dim is H or W
        if selected == node.selected_row || selected == node.selected_col {
            return Ok(EventResult::Continue);
        }
        let dim_size = dsattr.shape[selected] as isize;
        let current = node.selected_indexes[selected] as isize;
        let new_idx = (current + delta).rem_euclid(dim_size) as usize;
        node.selected_indexes[selected] = new_idx;
        if self.content_mode == ContentShowMode::Preview {
            self.img_state.indexes_to_load = node.selected_indexes[..ndim].to_vec();
            drop(node);
            self.send_image_load()
        } else {
            Ok(EventResult::Redraw)
        }
    }

    #[cfg_attr(not(test), allow(dead_code))]
    pub fn image_index_home(&mut self) -> Result<EventResult> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let mut node = current_node.node.borrow_mut();
        let Node::Dataset(_, dsattr) = &node.node else {
            return Ok(EventResult::Continue);
        };
        let ndim = dsattr.shape.len();
        let selected = node.selected_dim;
        if selected == node.selected_row || selected == node.selected_col {
            return Ok(EventResult::Continue);
        }
        node.selected_indexes[selected] = 0;
        if self.content_mode == ContentShowMode::Preview {
            self.img_state.indexes_to_load = node.selected_indexes[..ndim].to_vec();
            drop(node);
            self.send_image_load()
        } else {
            Ok(EventResult::Redraw)
        }
    }

    #[cfg_attr(not(test), allow(dead_code))]
    pub fn image_index_end(&mut self) -> Result<EventResult> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let mut node = current_node.node.borrow_mut();
        let Node::Dataset(_, dsattr) = &node.node else {
            return Ok(EventResult::Continue);
        };
        let ndim = dsattr.shape.len();
        let selected = node.selected_dim;
        if selected == node.selected_row || selected == node.selected_col {
            return Ok(EventResult::Continue);
        }
        node.selected_indexes[selected] = dsattr.shape[selected] - 1;
        if self.content_mode == ContentShowMode::Preview {
            self.img_state.indexes_to_load = node.selected_indexes[..ndim].to_vec();
            drop(node);
            self.send_image_load()
        } else {
            Ok(EventResult::Redraw)
        }
    }

    pub fn image_assign_dim(&mut self) -> Result<EventResult> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let mut node = current_node.node.borrow_mut();
        let Node::Dataset(_, _) = &node.node else {
            return Ok(EventResult::Continue);
        };
        let selected = node.selected_dim;
        if selected == node.selected_row || selected == node.selected_col {
            // On H or W → swap H and W
            let old_row = node.selected_row;
            node.selected_row = node.selected_col;
            node.selected_col = old_row;
            node.next_assign_is_w = false;
        } else if node.next_assign_is_w {
            // Stepping dim → becomes W
            node.selected_col = selected;
            node.next_assign_is_w = false;
        } else {
            // Stepping dim → becomes H
            node.selected_row = selected;
            node.next_assign_is_w = true;
        }
        if self.content_mode == ContentShowMode::Preview {
            drop(node);
            self.send_image_load()
        } else {
            self.matrix_view_state.row_offset = 0;
            self.matrix_view_state.col_offset = 0;
            Ok(EventResult::Redraw)
        }
    }

    /// Shape size of the currently selected dimension.
    pub fn current_dim_size(&self) -> usize {
        let node = self.treeview[self.tree_view_cursor].node.borrow();
        match &node.node {
            Node::Dataset(_, dsattr) => dsattr.shape.get(node.selected_dim).copied().unwrap_or(1),
            _ => 1,
        }
    }

    /// True when selected_dim is a stepping dim (not Row/Col).
    pub fn is_stepping_dim(&self) -> bool {
        let node = self.treeview[self.tree_view_cursor].node.borrow();
        node.selected_dim != node.selected_row && node.selected_dim != node.selected_col
    }

    /// Current position for the selected dim (index, row offset, or col offset).
    pub fn current_position(&self) -> usize {
        let node = self.treeview[self.tree_view_cursor].node.borrow();
        if node.selected_dim == node.selected_row {
            self.matrix_view_state.row_offset
        } else if node.selected_dim == node.selected_col {
            self.matrix_view_state.col_offset
        } else {
            node.selected_indexes[node.selected_dim]
        }
    }

    /// Set the absolute position for the selected dim. Used by hold acceleration
    /// to set the position directly from the time-based curve, avoiding
    /// accumulation drift that causes jumpy numbers on slow frames.
    pub fn dim_set_to(&mut self, target: usize) -> Result<EventResult> {
        let (selected_dim, selected_row, selected_col) = {
            let node = self.treeview[self.tree_view_cursor].node.borrow();
            (node.selected_dim, node.selected_row, node.selected_col)
        };

        if selected_dim == selected_row {
            if self.content_mode == ContentShowMode::Preview {
                return Ok(EventResult::Continue);
            }
            let node = self.treeview[self.tree_view_cursor].node.borrow();
            let Node::Dataset(_, dsattr) = &node.node else {
                return Ok(EventResult::Continue);
            };
            let max_offset = dsattr.shape[selected_row]
                .saturating_sub(self.matrix_view_state.rows_currently_available);
            drop(node);
            self.matrix_view_state.row_offset = target.min(max_offset);
            Ok(EventResult::Redraw)
        } else if selected_dim == selected_col {
            if self.content_mode == ContentShowMode::Preview {
                return Ok(EventResult::Continue);
            }
            let node = self.treeview[self.tree_view_cursor].node.borrow();
            let Node::Dataset(_, dsattr) = &node.node else {
                return Ok(EventResult::Continue);
            };
            let max_offset = dsattr.shape[selected_col]
                .saturating_sub(self.matrix_view_state.cols_currently_available);
            drop(node);
            self.matrix_view_state.col_offset = target.min(max_offset);
            Ok(EventResult::Redraw)
        } else {
            let mut node = self.treeview[self.tree_view_cursor].node.borrow_mut();
            let Node::Dataset(_, dsattr) = &node.node else {
                return Ok(EventResult::Continue);
            };
            let max_idx = dsattr.shape[selected_dim].saturating_sub(1);
            node.selected_indexes[selected_dim] = target.min(max_idx);
            Ok(EventResult::Redraw)
        }
    }

    /// Update selected dim index with clamping. Never wraps, never triggers image load.
    fn step_dim_index(&mut self, delta: isize) -> Result<EventResult> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let mut node = current_node.node.borrow_mut();
        let Node::Dataset(_, dsattr) = &node.node else {
            return Ok(EventResult::Continue);
        };
        let selected = node.selected_dim;
        if selected == node.selected_row || selected == node.selected_col {
            return Ok(EventResult::Continue);
        }
        let dim_size = dsattr.shape[selected];
        let current = node.selected_indexes[selected] as isize;
        let new_idx = (current + delta).clamp(0, dim_size as isize - 1) as usize;
        node.selected_indexes[selected] = new_idx;
        Ok(EventResult::Redraw)
    }

    /// Unified navigation: applies step `n` in `direction` based on what selected_dim is.
    /// - Stepping dim → clamp index (no image load — caller decides)
    /// - Row dim (matrix) → scroll rows
    /// - Col dim (matrix) → scroll cols
    /// - Row/Col dim (preview) → no-op
    pub fn dim_navigate(&mut self, direction: isize, n: usize) -> Result<EventResult> {
        let (selected_dim, selected_row, selected_col) = {
            let node = self.treeview[self.tree_view_cursor].node.borrow();
            (node.selected_dim, node.selected_row, node.selected_col)
        };

        if selected_dim == selected_row {
            if self.content_mode == ContentShowMode::Preview {
                return Ok(EventResult::Continue);
            }
            if direction < 0 { self.up(n) } else { self.down(n) }
        } else if selected_dim == selected_col {
            if self.content_mode == ContentShowMode::Preview {
                return Ok(EventResult::Continue);
            }
            let delta = if direction < 0 { -(n as isize) } else { n as isize };
            self.matrix_scroll_col(delta)
        } else {
            let delta = if direction < 0 { -(n as isize) } else { n as isize };
            self.step_dim_index(delta)
        }
    }

    pub fn matrix_scroll_col(&mut self, delta: isize) -> Result<EventResult> {
        let node = self.treeview[self.tree_view_cursor].node.borrow();
        let Node::Dataset(_, dsattr) = &node.node else {
            return Ok(EventResult::Continue);
        };
        let col_shape = dsattr.shape[node.selected_col];
        let max_offset = col_shape.saturating_sub(self.matrix_view_state.cols_currently_available);
        drop(node);
        if delta > 0 {
            self.matrix_view_state.col_offset =
                (self.matrix_view_state.col_offset + delta as usize).min(max_offset);
        } else {
            self.matrix_view_state.col_offset = self
                .matrix_view_state
                .col_offset
                .saturating_sub((-delta) as usize);
        }
        Ok(EventResult::Redraw)
    }

    pub fn left(&mut self, arg: isize) -> Result<EventResult> {
        match self.content_mode {
            ContentShowMode::Preview => match self.segment_state.segumented {
                SegmentType::Image => Ok(EventResult::Continue),
                SegmentType::Chart => Ok(EventResult::Continue),
                SegmentType::NoSegment => {
                    let current_node = &self.treeview[self.tree_view_cursor];
                    let mut node = current_node.node.borrow_mut();
                    let new_col_offset = node.col_offset.saturating_sub(arg).max(0);
                    node.col_offset = new_col_offset;
                    Ok(EventResult::Redraw)
                }
            },
            ContentShowMode::Matrix => self.change_col(-arg),
        }
    }

    /// Find sibling image datasets for the currently selected dataset.
    /// Returns paths of other image datasets in the same parent group.
    pub fn find_image_siblings(&self) -> Vec<(String, String, crate::h5f::ImageType)> {
        let current_node = &self.treeview[self.tree_view_cursor];
        let node = current_node.node.borrow();
        let (current_path, _current_filename) = match &node.node {
            Node::Dataset(_, dsattr) => {
                if dsattr.image.is_none() {
                    return vec![];
                }
                (dsattr.full_path.clone(), dsattr.filename.clone())
            }
            _ => return vec![],
        };
        drop(node);

        // Get parent path
        let parent_path = current_path
            .rsplit_once('/')
            .map(|(parent, _)| parent.to_string())
            .unwrap_or_default();

        // Walk treeview to find sibling image datasets
        let mut siblings = Vec::new();
        for item in &self.treeview {
            let node = item.node.borrow();
            if let Node::Dataset(_, dsattr) = &node.node {
                if dsattr.full_path == current_path {
                    continue; // skip self
                }
                if let Some(ref img_type) = dsattr.image {
                    let item_parent = dsattr
                        .full_path
                        .rsplit_once('/')
                        .map(|(p, _)| p.to_string())
                        .unwrap_or_default();
                    if item_parent == parent_path {
                        siblings.push((
                            dsattr.full_path.clone(),
                            dsattr.filename.clone(),
                            img_type.clone(),
                        ));
                    }
                }
            }
        }
        siblings.truncate(3); // max 3 siblings (4 total with primary)
        siblings
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_helpers::make_test_state;

    // ── image_move_dim ──────────────────────────────────────────────

    #[test]
    fn move_dim_cycles_forward_through_all_dims() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        // Default: selected_row=0, selected_col=1, selected_dim starts at 0
        // but H5FNode defaults: selected_dim=0. The render init would fix this
        // but we're testing the method directly, so manually set selected_dim.
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 0;
        }

        // Move right through all 4 dims: 0 -> 1 -> 2 -> 3 -> 0 (wraps)
        let dims: Vec<usize> = (0..5)
            .map(|_| {
                state.image_move_dim(1).unwrap();
                state.treeview[state.tree_view_cursor]
                    .node
                    .borrow()
                    .selected_dim
            })
            .collect();
        assert_eq!(dims, vec![1, 2, 3, 0, 1], "should cycle forward through all dims including H/W");
    }

    #[test]
    fn move_dim_cycles_backward_through_all_dims() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 0;
        }

        // Move left: 0 -> 3 -> 2 -> 1 -> 0 (wraps backward)
        let dims: Vec<usize> = (0..5)
            .map(|_| {
                state.image_move_dim(-1).unwrap();
                state.treeview[state.tree_view_cursor]
                    .node
                    .borrow()
                    .selected_dim
            })
            .collect();
        assert_eq!(dims, vec![3, 2, 1, 0, 3], "should cycle backward through all dims");
    }

    #[test]
    fn move_dim_visits_h_and_w_dims() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        // selected_row=0 (H), selected_col=1 (W)
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 3; // Start from last dim
        }

        // Move right: 3 -> 0 (H dim) -> 1 (W dim)
        state.image_move_dim(1).unwrap();
        let dim = state.treeview[state.tree_view_cursor].node.borrow().selected_dim;
        assert_eq!(dim, 0, "cursor should land on H dim");

        state.image_move_dim(1).unwrap();
        let dim = state.treeview[state.tree_view_cursor].node.borrow().selected_dim;
        assert_eq!(dim, 1, "cursor should land on W dim");
    }

    // ── image_change_index ──────────────────────────────────────────

    #[test]
    fn change_index_wraps_forward() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2; // dim with size 20
            node.selected_indexes[2] = 18;
        }

        // Step +1 from 18 -> 19
        state.image_change_index(1).unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[2];
        assert_eq!(idx, 19);

        // Step +1 from 19 -> 0 (wraps)
        state.image_change_index(1).unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[2];
        assert_eq!(idx, 0, "should wrap from max to 0");
    }

    #[test]
    fn change_index_wraps_backward() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2; // dim with size 20
            node.selected_indexes[2] = 1;
        }

        // Step -1 from 1 -> 0
        state.image_change_index(-1).unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[2];
        assert_eq!(idx, 0);

        // Step -1 from 0 -> 19 (wraps)
        state.image_change_index(-1).unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[2];
        assert_eq!(idx, 19, "should wrap from 0 to max");
    }

    #[test]
    fn change_index_noop_on_h_dim() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 0; // H dim (selected_row=0)
            node.selected_indexes[0] = 2;
        }

        let result = state.image_change_index(1).unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[0];
        assert_eq!(idx, 2, "index should not change on H dim");
        assert!(matches!(result, EventResult::Continue));
    }

    #[test]
    fn change_index_noop_on_w_dim() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 1; // W dim (selected_col=1)
            node.selected_indexes[1] = 3;
        }

        let result = state.image_change_index(1).unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[1];
        assert_eq!(idx, 3, "index should not change on W dim");
        assert!(matches!(result, EventResult::Continue));
    }

    #[test]
    fn change_index_page_jump_wraps() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2; // dim with size 20
            node.selected_indexes[2] = 15;
        }

        // Page down (+10) from 15 -> wraps: (15+10) % 20 = 5
        state.image_change_index(10).unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[2];
        assert_eq!(idx, 5, "page jump should wrap around");
    }

    #[test]
    fn change_index_updates_indexes_to_load() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2;
            node.selected_indexes[2] = 0;
        }

        state.image_change_index(3).unwrap();
        assert_eq!(
            state.img_state.indexes_to_load[2], 3,
            "indexes_to_load should be updated for image reload"
        );
    }

    // ── image_index_home / image_index_end ──────────────────────────

    #[test]
    fn index_home_jumps_to_zero() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2;
            node.selected_indexes[2] = 15;
        }

        state.image_index_home().unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[2];
        assert_eq!(idx, 0, "Home should jump to index 0");
    }

    #[test]
    fn index_end_jumps_to_max() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2; // dim size = 20
            node.selected_indexes[2] = 5;
        }

        state.image_index_end().unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[2];
        assert_eq!(idx, 19, "End should jump to last index (shape-1)");
    }

    #[test]
    fn index_home_noop_on_h_dim() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 0; // H dim
            node.selected_indexes[0] = 3;
        }

        let result = state.image_index_home().unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[0];
        assert_eq!(idx, 3, "Home should be no-op on H dim");
        assert!(matches!(result, EventResult::Continue));
    }

    #[test]
    fn index_end_noop_on_w_dim() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 1; // W dim
            node.selected_indexes[1] = 3;
        }

        let result = state.image_index_end().unwrap();
        let idx = state.treeview[state.tree_view_cursor].node.borrow().selected_indexes[1];
        assert_eq!(idx, 3, "End should be no-op on W dim");
        assert!(matches!(result, EventResult::Continue));
    }

    // ── image_assign_dim (Enter key) ────────────────────────────────

    #[test]
    fn assign_dim_stepping_becomes_h() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        // Initially: H=dim0, W=dim1
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2; // a stepping dim
        }

        state.image_assign_dim().unwrap();
        let node = state.treeview[state.tree_view_cursor].node.borrow();
        assert_eq!(node.selected_row, 2, "stepping dim should become new H");
        assert_eq!(node.selected_col, 1, "W should stay unchanged");
    }

    #[test]
    fn assign_dim_on_h_swaps_h_and_w() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        // H=0, W=1
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 0; // cursor on H dim
        }

        state.image_assign_dim().unwrap();
        let node = state.treeview[state.tree_view_cursor].node.borrow();
        assert_eq!(node.selected_row, 1, "H should become old W");
        assert_eq!(node.selected_col, 0, "W should become old H");
    }

    #[test]
    fn assign_dim_on_w_swaps_h_and_w() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        // H=0, W=1
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 1; // cursor on W dim
        }

        state.image_assign_dim().unwrap();
        let node = state.treeview[state.tree_view_cursor].node.borrow();
        assert_eq!(node.selected_row, 1, "H should become old W");
        assert_eq!(node.selected_col, 0, "W should become old H");
    }

    #[test]
    fn assign_dim_twice_makes_dim_w() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        // Initially: H=0, W=1.
        // Step 1: Enter on dim2 (stepping) -> H=2, W=1, toggle flips to true
        // Step 2: Enter on dim3 (stepping) -> W=3, toggle flips to false
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2;
        }
        state.image_assign_dim().unwrap(); // dim2 becomes H
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 3;
        }
        state.image_assign_dim().unwrap(); // dim3 becomes W

        let node = state.treeview[state.tree_view_cursor].node.borrow();
        assert_eq!(node.selected_row, 2, "first Enter assigns H=2");
        assert_eq!(node.selected_col, 3, "second Enter assigns W=3");
    }

    #[test]
    fn assign_dim_alternates_h_then_w() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30, 40]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        // 5D dataset: H=0, W=1, stepping dims: 2,3,4
        // Enter on dim2 → H=2 (toggle true)
        // Enter on dim3 → W=3 (toggle false)
        // Enter on dim4 → H=4 (toggle true)
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2;
        }
        state.image_assign_dim().unwrap();
        {
            let node = state.treeview[state.tree_view_cursor].node.borrow();
            assert_eq!(node.selected_row, 2, "1st Enter: stepping dim becomes H");
            assert_eq!(node.selected_col, 1, "1st Enter: W unchanged");
            assert!(node.next_assign_is_w, "toggle should be true after H assign");
        }

        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 3;
        }
        state.image_assign_dim().unwrap();
        {
            let node = state.treeview[state.tree_view_cursor].node.borrow();
            assert_eq!(node.selected_row, 2, "2nd Enter: H unchanged");
            assert_eq!(node.selected_col, 3, "2nd Enter: stepping dim becomes W");
            assert!(!node.next_assign_is_w, "toggle should be false after W assign");
        }

        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 4;
        }
        state.image_assign_dim().unwrap();
        {
            let node = state.treeview[state.tree_view_cursor].node.borrow();
            assert_eq!(node.selected_row, 4, "3rd Enter: stepping dim becomes H again");
            assert_eq!(node.selected_col, 3, "3rd Enter: W unchanged");
        }
    }

    #[test]
    fn assign_dim_swap_resets_toggle() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        // Enter on stepping dim2 → H=2, toggle=true
        // Enter on H dim (swap) → toggle resets to false
        // Enter on stepping dim3 → should assign H (not W)
        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2;
        }
        state.image_assign_dim().unwrap(); // dim2 → H, toggle=true

        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 2; // cursor on H dim
        }
        state.image_assign_dim().unwrap(); // swap H↔W, toggle=false

        {
            let node = state.treeview[state.tree_view_cursor].node.borrow();
            assert!(!node.next_assign_is_w, "swap should reset toggle to false");
        }

        {
            let mut node = state.treeview[state.tree_view_cursor].node.borrow_mut();
            node.selected_dim = 3; // stepping dim
        }
        state.image_assign_dim().unwrap(); // should assign H (toggle was false)

        let node = state.treeview[state.tree_view_cursor].node.borrow();
        assert_eq!(node.selected_row, 3, "after swap reset, next Enter assigns H");
    }

    // ── change_row / change_col match guard fix ─────────────────────

    #[test]
    fn change_row_works_in_matrix_mode() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        state.content_mode = ContentShowMode::Matrix;
        // Initially: selected_row=0, selected_col=1

        let result = state.change_row(1).unwrap();
        assert!(matches!(result, EventResult::Redraw));

        let node = state.treeview[state.tree_view_cursor].node.borrow();
        // Row should have moved from 0 to 2 (skipping col=1)
        assert_ne!(node.selected_row, 0, "row should have changed in Matrix mode");
    }

    #[test]
    fn change_col_works_in_matrix_mode() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        state.content_mode = ContentShowMode::Matrix;

        let result = state.change_col(1).unwrap();
        assert!(matches!(result, EventResult::Redraw));

        let node = state.treeview[state.tree_view_cursor].node.borrow();
        assert_ne!(node.selected_col, 1, "col should have changed in Matrix mode");
    }

    #[test]
    fn change_row_noop_in_preview_mode() {
        let Some(mut state) = make_test_state(&[5, 10, 20, 30]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        state.content_mode = ContentShowMode::Preview;

        let result = state.change_row(1).unwrap();
        assert!(matches!(result, EventResult::Continue),
            "change_row should be no-op in Preview mode (use image_assign_dim instead)");
    }

    // ── NavAccel: tap detection ─────────────────────────────────────

    #[test]
    fn nav_single_tap_returns_1() {
        let mut nav = NavAccel::new();
        std::thread::sleep(std::time::Duration::from_millis(250));
        let step = nav.on_press(KeyCode::Down, 100);
        assert_eq!(step, 1, "single tap should return step=1");
    }

    #[test]
    fn nav_double_tap_returns_5pct() {
        let mut nav = NavAccel::new();
        // First press
        std::thread::sleep(std::time::Duration::from_millis(250));
        let s1 = nav.on_press(KeyCode::Down, 100);
        assert_eq!(s1, 1, "first tap = 1");

        // Quick second press within 200ms window
        std::thread::sleep(std::time::Duration::from_millis(80));
        let s2 = nav.on_press(KeyCode::Down, 100);
        assert_eq!(s2, 5, "double tap on dim_size=100 should return 100/20=5");
    }

    #[test]
    fn nav_triple_tap_returns_dim_size() {
        let mut nav = NavAccel::new();
        std::thread::sleep(std::time::Duration::from_millis(250));
        nav.on_press(KeyCode::Down, 200);

        std::thread::sleep(std::time::Duration::from_millis(80));
        nav.on_press(KeyCode::Down, 200);

        std::thread::sleep(std::time::Duration::from_millis(80));
        let s3 = nav.on_press(KeyCode::Down, 200);
        assert_eq!(s3, 200, "triple tap returns dim_size (home/end, clamped by caller)");
    }

    #[test]
    fn nav_slow_repeated_pressing_never_multitap() {
        let mut nav = NavAccel::new();
        // Press with gaps > 200ms — each should be step=1
        for i in 0..5 {
            std::thread::sleep(std::time::Duration::from_millis(250));
            let step = nav.on_press(KeyCode::Down, 100);
            assert_eq!(step, 1, "slow press #{i} should always be step=1");
        }
    }

    #[test]
    fn nav_hold_invalidates_multitap() {
        let mut nav = NavAccel::new();
        // First press
        std::thread::sleep(std::time::Duration::from_millis(250));
        nav.on_press(KeyCode::Down, 100);

        // Hold generates repeat events → resets tap_count
        nav.on_repeat(0, 1, 100);
        nav.on_release();

        // Quick second press — should NOT be a double-tap because hold reset tap_count
        std::thread::sleep(std::time::Duration::from_millis(80));
        let step = nav.on_press(KeyCode::Down, 100);
        assert_eq!(step, 1, "press after hold should be step=1, not double-tap");
    }

    #[test]
    fn nav_different_key_resets_multitap() {
        let mut nav = NavAccel::new();
        std::thread::sleep(std::time::Duration::from_millis(250));
        nav.on_press(KeyCode::Down, 100);

        std::thread::sleep(std::time::Duration::from_millis(80));
        let step = nav.on_press(KeyCode::Up, 100);
        assert_eq!(step, 1, "switching direction should reset tap count");
    }

    // ── NavAccel: hold_target curve ─────────────────────────────────

    /// Helper: call hold_target with default config values.
    fn ht(t: f64, origin: usize, direction: isize, dim_size: usize) -> usize {
        let nc = NavigationConfig::default();
        NavAccel::hold_target(t, origin, direction, dim_size,
            nc.hold_traverse_secs, nc.min_hold_velocity, nc.max_hold_velocity_steps,
            nc.max_hold_velocity_pct)
    }

    #[test]
    fn hold_target_forward_from_origin_zero() {
        // Velocity ramps from min(3) to max(50) over traverse_secs(12).
        // dim_size=1000: max_vel = max(50, 1000*0.05) = 50
        // At t=0: v=3, displacement grows smoothly
        let nc = NavigationConfig::default();
        let tsec = nc.hold_traverse_secs;
        let times = [0.0, 0.5, 1.0, 2.0, 4.0, tsec * 0.5, tsec, tsec + 20.0];
        let targets: Vec<usize> = times
            .iter()
            .map(|&t| ht(t, 0, 1, 1000))
            .collect();

        assert_eq!(targets[0], 0, "t=0: no displacement");
        // Monotonically increasing
        for i in 1..targets.len() {
            assert!(targets[i] >= targets[i - 1],
                "targets should be monotonically increasing: t[{}]={} >= t[{}]={}",
                i, targets[i], i - 1, targets[i - 1]);
        }
        // At t=0.5: min_vel=3, so displacement ~ 3*0.5 + small accel ≈ 1-2
        assert!(targets[1] >= 1, "t=0.5: should have moved at least 1 (got {})", targets[1]);
        // After traverse + extra time at max vel, should eventually hit the end
        assert_eq!(targets[7], 999, "after ramp + coast: should reach end");
    }

    #[test]
    fn hold_target_backward_from_end() {
        let tsec = NavigationConfig::default().hold_traverse_secs;
        let targets: Vec<usize> = [0.0, 0.5, 1.0, 4.0, tsec, tsec + 20.0]
            .iter()
            .map(|&t| ht(t, 999, -1, 1000))
            .collect();

        assert_eq!(targets[0], 999, "t=0: at origin");
        for i in 1..targets.len() {
            assert!(targets[i] <= targets[i - 1],
                "backward should be monotonically decreasing: t[{}]={} <= t[{}]={}",
                i, targets[i], i - 1, targets[i - 1]);
        }
        // With enough coast time at max_vel, eventually reaches 0
        assert_eq!(targets[5], 0, "after ramp + coast: should reach 0");
    }

    #[test]
    fn hold_target_forward_from_midpoint() {
        let tsec = NavigationConfig::default().hold_traverse_secs;
        let origin = 500;
        let dim_size = 1000;
        let targets: Vec<usize> = [0.0, 1.0, tsec * 0.5, tsec + 10.0]
            .iter()
            .map(|&t| ht(t, origin, 1, dim_size))
            .collect();

        assert_eq!(targets[0], 500, "t=0: at origin");
        assert!(targets[1] > 500, "t=1.0: should have moved (got {})", targets[1]);
        assert!(targets[2] > targets[1], "t=half: still accelerating");
        assert_eq!(targets[3], 999, "after ramp + coast: should clamp at end");
    }

    #[test]
    fn hold_target_small_dim_responsive() {
        // dim_size=10: max_vel = max(50, 10*0.05) = 50
        // min_vel=3, ramp from 3→50 over 12s
        // At t=0.5: displacement ~ 3*0.5 + small accel ≈ 1
        let targets: Vec<usize> = [0.0, 0.5, 1.0, 2.0, 3.0, 4.0]
            .iter()
            .map(|&t| ht(t, 0, 1, 10))
            .collect();

        assert_eq!(targets[0], 0, "t=0: no movement");
        assert!(targets[1] >= 1, "t=0.5: should have first step (got {})", targets[1]);
        assert!(targets[2] >= 3, "t=1.0s: at least 3 steps (got {})", targets[2]);
        assert_eq!(targets[5], 9, "t=4.0s: stays clamped at end");
    }

    #[test]
    fn hold_target_large_dim_fast_start() {
        // dim_size=10000: max_vel = max(50, 10000*0.05) = 500
        // min_vel=3, ramp from 3→500 over 12s
        // At t=0.1: displacement ~ 3*0.1 = 0.3 → rounds to 0, but with accel it's a bit more
        let targets: Vec<usize> = [0.0, 0.5, 1.0, 2.0, 5.0]
            .iter()
            .map(|&t| ht(t, 0, 1, 10000))
            .collect();

        assert_eq!(targets[0], 0);
        assert!(targets[1] >= 1, "t=0.5s: should have moved (got {})", targets[1]);
        assert!(targets[2] >= 3, "t=1.0s: should be >=3 (got {})", targets[2]);
        assert!(targets[4] >= 50, "t=5.0s: well into acceleration (got {})", targets[4]);
    }

    #[test]
    fn hold_target_smooth_frame_rate_independence() {
        let dim_size = 500;
        let origin = 0;

        // Simulate 60fps: sample at every ~16ms for 2 seconds
        let targets_60fps: Vec<usize> = (0..=120)
            .map(|i| {
                let t = i as f64 * (1.0 / 60.0);
                ht(t, origin, 1, dim_size)
            })
            .collect();

        // Simulate 10fps (slow preview): sample at every 100ms for 2 seconds
        let targets_10fps: Vec<usize> = (0..=20)
            .map(|i| {
                let t = i as f64 * 0.1;
                ht(t, origin, 1, dim_size)
            })
            .collect();

        // At t=1.0s: both should give the same value
        assert_eq!(targets_60fps[60], targets_10fps[10],
            "same elapsed time must give same position regardless of frame rate");
        assert_eq!(targets_60fps[120], targets_10fps[20],
            "same elapsed time must give same position at t=2s");

        // 60fps should be monotonically increasing (smooth)
        let mut max_delta = 0usize;
        for i in 1..targets_60fps.len() {
            assert!(targets_60fps[i] >= targets_60fps[i - 1],
                "60fps should be monotonically increasing at frame {}", i);
            let delta = targets_60fps[i] - targets_60fps[i - 1];
            if delta > max_delta { max_delta = delta; }
        }
        assert!(max_delta <= 20,
            "60fps max per-frame delta should be bounded (got {})", max_delta);

        let mut max_delta_slow = 0usize;
        for i in 1..targets_10fps.len() {
            assert!(targets_10fps[i] >= targets_10fps[i - 1],
                "10fps should be monotonically increasing at frame {}", i);
            let delta = targets_10fps[i] - targets_10fps[i - 1];
            if delta > max_delta_slow { max_delta_slow = delta; }
        }
    }

    #[test]
    fn hold_target_print_curves() {
        // Verbose test: print the acceleration curve for manual inspection.
        // Run with: cargo test hold_target_print_curves -- --nocapture
        let nc = NavigationConfig::default();
        println!("\nConfig: traverse={:.1}s, min_vel={}, max_vel_steps={}, max_vel_pct={}",
            nc.hold_traverse_secs, nc.min_hold_velocity, nc.max_hold_velocity_steps,
            nc.max_hold_velocity_pct);
        let dims = [10, 100, 1000, 10000];
        for &dim in &dims {
            println!("\n--- dim_size={dim}, origin=0, direction=+1 ---");
            println!("{:>6}  {:>8}  {:>6}  {:>10}", "t(s)", "position", "delta", "vel(pos/s)");
            let mut prev = 0usize;
            let mut prev_t = 0.0f64;
            let steps = (nc.hold_traverse_secs * 10.0) as usize + 2;
            for i in 0..=steps {
                let t = i as f64 * 0.1;
                let pos = ht(t, 0, 1, dim);
                let delta = pos.saturating_sub(prev);
                let dt = t - prev_t;
                let vel = if dt > 0.0 { delta as f64 / dt } else { 0.0 };
                println!("{t:>6.1}  {pos:>8}  {delta:>6}  {vel:>10.1}");
                prev = pos;
                prev_t = t;
            }
        }
    }

    // ── execute_command tests ─────────────────────────────────────

    #[test]
    fn execute_quit() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        let result = state.execute_command(&Command::Quit).unwrap();
        assert!(matches!(result, EventResult::Quit));
    }

    #[test]
    fn execute_help() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        let result = state.execute_command(&Command::Help).unwrap();
        assert!(matches!(result, EventResult::Redraw));
        assert!(matches!(state.mode, Mode::Help));
    }

    #[test]
    fn execute_settings() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        let result = state.execute_command(&Command::Settings).unwrap();
        assert!(matches!(result, EventResult::Redraw));
        assert!(matches!(state.mode, Mode::Settings));
    }

    #[test]
    fn execute_noop() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        let result = state.execute_command(&Command::Noop).unwrap();
        assert!(matches!(result, EventResult::Redraw));
        assert!(matches!(state.mode, Mode::Normal));
    }

    #[test]
    fn execute_increment() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        let result = state.execute_command(&Command::Increment(5)).unwrap();
        assert!(matches!(result, EventResult::Redraw));
    }

    #[test]
    fn execute_decrement() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        let result = state.execute_command(&Command::Decrement(3)).unwrap();
        assert!(matches!(result, EventResult::Redraw));
    }

    #[test]
    fn execute_seek() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        let result = state.execute_command(&Command::Seek(0)).unwrap();
        assert!(matches!(result, EventResult::Redraw));
    }

    #[test]
    fn reexecute_repeats() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        state.command_state.command_buffer = "+5".to_string();
        state.command_state.parse_command().unwrap();
        assert!(matches!(state.command_state.last_command, Command::Increment(5)));
        let result = state.reexecute_command().unwrap();
        assert!(matches!(result, EventResult::Redraw));
    }

    // ── multi-image sibling detection ────────────────────────────────

    #[test]
    fn find_image_siblings_returns_others_in_same_group() {
        let Some(state) = crate::test_helpers::make_multi_image_state(3, &[64, 64]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        let siblings = state.find_image_siblings();
        // cursor is on img_0 → should find img_1 and img_2
        assert_eq!(siblings.len(), 2);
        for (path, _name, img_type) in &siblings {
            assert!(path.starts_with("/images/img_"));
            assert!(matches!(img_type, crate::h5f::ImageType::Grayscale));
        }
    }

    #[test]
    fn find_image_siblings_empty_for_non_image() {
        // make_test_state creates a plain u8 dataset (no IMAGE attrs)
        let Some(state) = make_test_state(&[10, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        let siblings = state.find_image_siblings();
        assert!(siblings.is_empty());
    }

    #[test]
    fn find_image_siblings_truncates_to_3() {
        let Some(state) = crate::test_helpers::make_multi_image_state(6, &[32, 32]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        let siblings = state.find_image_siblings();
        // 6 images total, cursor on one → 5 siblings, truncated to 3
        assert_eq!(siblings.len(), 3);
    }
}
