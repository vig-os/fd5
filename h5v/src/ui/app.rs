use std::{
    io::stdout,
    rc::Rc,
    sync::{
        mpsc::{channel, Sender},
        Arc, Mutex,
    },
    thread,
};

use arboard::Clipboard;
use ratatui::{
    crossterm::{
        event::{self},
        terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
        ExecutableCommand,
    },
    layout::{Alignment, Constraint, Layout, Rect},
    prelude::CrosstermBackend,
    style::{Color, Style},
    text::Text,
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame, Terminal,
};
use ratatui_image::picker::Picker;

use crate::{
    config::Config,
    error::{log_error, AppError},
    h5f,
    ui::{
        input::EventResult,
        mchart::MultiChartState,
        preload::{PreloadCache, spawn_preload},
    },
};

use super::{
    command::{Command, CommandState},
    command_view::render_command_dialog,
    help::render_help,
    hints::{hint_rows_needed, render_hint_bar},
    image_preview::{
        handle_image_load, handle_image_resize, handle_imagefs_load, handle_imagefsvlen_load,
        ImageLoadedResult, ImageResizeResult,
    },
    input::handle_input_event,
    main_display::render_main_display,
    settings::render_settings,
    state::{
        self, AppState, AttributeCursor, ContentShowMode, Focus, ImgState, LastFocused,
        MatrixViewState, Mode, SettingsState,
    },
    tree_view::render_tree,
};

fn make_panels_rect(area: Rect, mode: Mode, cfg: &Config) -> Rc<[Rect]> {
    if let Mode::Search = mode {

        Layout::default()
            .direction(ratatui::layout::Direction::Horizontal)
            .constraints([Constraint::Percentage(100), Constraint::Percentage(0)])
            .split(area)
    } else {
        if area.width < cfg.ui.narrow_threshold {
            let chunks = Layout::default()
                .direction(ratatui::layout::Direction::Horizontal)
                .constraints([Constraint::Percentage(100), Constraint::Percentage(0)])
                .split(area);
            return chunks;
        }
        let content_pct = 100u16.saturating_sub(cfg.ui.tree_panel_pct);
        Layout::default()
            .direction(ratatui::layout::Direction::Horizontal)
            .constraints([Constraint::Percentage(cfg.ui.tree_panel_pct), Constraint::Percentage(content_pct)])
            .split(area)
    }
}

type Result<T> = std::result::Result<T, AppError>;

pub struct IntendedMainLoopBreak {}

pub fn init(filename: String, cfg: Config, swmr: bool) -> Result<()> {
    stdout().execute(EnterAlternateScreen)?;
    enable_raw_mode()?;
    let mut terminal = Terminal::new(CrosstermBackend::new(stdout()))?;
    terminal.clear()?;

    let mut last_message = None;

    match main_recover_loop(&mut terminal, filename.clone(), cfg, swmr) {
        Ok(_) => {}
        Err(e) => {
            last_message = Some(format!("{}", e));
        }
    }

    stdout().execute(LeaveAlternateScreen)?;
    disable_raw_mode()?;
    if let Some(message) = &last_message {
        eprintln!("Unrecoverable AppError: {}", message);
        // Also write to file in case stderr is lost with alternate screen
        if let Ok(mut f) = std::fs::File::create("/tmp/h5v_crash.log") {
            let _ = std::io::Write::write_fmt(&mut f, format_args!("AppError: {}\n", message));
        }
    }
    Ok(())
}

fn main_recover_loop(
    terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>,
    filename: String,
    cfg: Config,
    swmr: bool,
) -> Result<IntendedMainLoopBreak> {
    let file_path = std::path::PathBuf::from(&filename);
    let h5f = h5f::H5F::open_with_mode(filename, swmr).map_err(|e| {
        AppError::Hdf5(hdf5_metno::Error::from(format!(
            "Failed to open HDF5 file: {}",
            e
        )))
    })?;

    let (tx_events, rx_events) = channel();
    let picker = Picker::from_query_stdio().unwrap_or(Picker::halfblocks());
    let tx_events_2 = tx_events.clone();
    let tx_resize_worker = handle_image_resize(tx_events_2);
    let tx_load_imgfs = handle_imagefs_load(tx_events.clone(), tx_resize_worker.clone(), picker.clone());
    let tx_load_imgfsvlen =
        handle_imagefsvlen_load(tx_events.clone(), tx_resize_worker.clone(), picker.clone());
    let preload_cache = Arc::new(Mutex::new(PreloadCache::new(cfg.cache.preload_mb * 1024 * 1024)));
    let tx_load_img = handle_image_load(tx_events.clone(), tx_resize_worker.clone(), picker.clone(), preload_cache.clone());

    let img_state = ImgState {
        protocol: None,
        tx_load_imgfs,
        tx_load_imgfsvlen,
        tx_load_img,
        ds: None,
        idx_to_load: 0,
        idx_loaded: -1,
        indexes_to_load: vec![],
        indexes_loaded: vec![],
        img_dims_loaded: (0, 1),
        error: None,
        picker: picker.clone(),
        tx_events: Some(tx_events.clone()),
        tx_resize: Some(tx_resize_worker.clone()),
    };

    let matrix_view_state = MatrixViewState {
        col_offset: 0,
        row_offset: 0,
        rows_currently_available: 0,
        cols_currently_available: 0,
    };
    let clipboard = Clipboard::new()
        .map_err(|e| AppError::ClipboardError(format!("Failed to initialize clipboard: {}", e)))?;

    let segment_state = state::SegmentState {
        idx: 0,
        segment_count: 0,
        segumented: state::SegmentType::NoSegment,
    };

    let command_state = CommandState {
        command_buffer: String::new(),
        last_command: Command::Noop,
        cursor: 0,
    };

    let mut state = AppState {
        root: h5f.root.clone(),
        multi_chart: MultiChartState::new(picker.clone()),
        segment_state,
        command_state,
        treeview: vec![],
        tree_view_cursor: 0,
        attributes_view_cursor: AttributeCursor {
            attribute_index: 0,
            attribute_offset: 0,
            attribute_view_selection: state::AttributeViewSelection::Name,
        },
        focus: Focus::Tree(LastFocused::Attributes),
        clipboard,
        mode: Mode::Normal,
        copying: false,
        searcher: None,
        show_tree_view: true,
        content_mode: ContentShowMode::Preview,
        img_state,
        matrix_view_state,
        preload_cache: preload_cache.clone(),
        nav_accel: state::NavAccel::from_config(&cfg.navigation),
        settings_state: SettingsState::from_config(&cfg),
        cfg,
        chart_log_y: false,
        chart_log_x: false,
        chart_mode: state::ChartMode::Line,
        window_center: None,
        window_width: None,
        auto_window: true,
        multi_image_mode: false,
        multi_image_siblings: vec![],
        fd5_status: Some(fd5::Fd5Status::Checking),
        fd5_file_path: Some(file_path.clone()),
    };

    state.compute_tree_view();

    // Spawn background preload of all previewable datasets
    let datasets = h5f::collect_dataset_info(&state.root);
    spawn_preload(preload_cache, datasets, state.cfg.cache.max_dataset_mb);

    // Spawn background fd5 verification
    {
        let tx = tx_events.clone();
        let fp = file_path.clone();
        thread::spawn(move || {
            let status = match fd5::verify(&fp) {
                Ok(s) => s,
                Err(e) => fd5::Fd5Status::Error(format!("{}", e)),
            };
            let _ = tx.send(AppEvent::Fd5VerifyComplete(status));
        });
    }

    let draw_closure = |frame: &mut Frame, state: &mut AppState| {
        // Full-screen modes: render alone with hint bar
        match state.mode {
            Mode::Help => {
                let hh = hint_rows_needed(state, frame.area().width, 2);
                let chunks = Layout::default()
                    .direction(ratatui::layout::Direction::Vertical)
                    .constraints([Constraint::Min(1), Constraint::Length(hh)])
                    .split(frame.area());
                render_help(frame, chunks[0]);
                render_hint_bar(frame, chunks[1], state);
                return;
            }
            Mode::MultiChart => {
                let hh = hint_rows_needed(state, frame.area().width, 2);
                let chunks = Layout::default()
                    .direction(ratatui::layout::Direction::Vertical)
                    .constraints([Constraint::Min(1), Constraint::Length(hh)])
                    .split(frame.area());
                state.multi_chart.render(frame);
                render_hint_bar(frame, chunks[1], state);
                return;
            }
            Mode::Settings => {
                let hh = hint_rows_needed(state, frame.area().width, 2);
                let chunks = Layout::default()
                    .direction(ratatui::layout::Direction::Vertical)
                    .constraints([Constraint::Min(1), Constraint::Length(hh)])
                    .split(frame.area());
                render_settings(frame, state);
                render_hint_bar(frame, chunks[1], state);
                return;
            }
            _ => {}
        }

        // Split off rows at the bottom for the hint bar (auto-sized)
        let hint_h = hint_rows_needed(state, frame.area().width, 3);
        let outer = Layout::default()
            .direction(ratatui::layout::Direction::Vertical)
            .constraints([Constraint::Min(1), Constraint::Length(hint_h)])
            .split(frame.area());
        let body_area = outer[0];
        let hint_area = outer[1];

        let show_tree_view = state.show_tree_view;

        let (tree_area_opt, main_display_area) = match show_tree_view {
            true => {
                let areas = make_panels_rect(body_area, state.mode.clone(), &state.cfg);
                let (tree_area, main_display_area) = (areas[0], areas[1]);
                render_tree(frame, tree_area, state);
                (Some(tree_area), main_display_area)
            }
            false => (None, body_area),
        };

        // Always render main content (Normal, Command, Search all show it)
        match state.mode {
            Mode::Search => {} // tree_view handles search rendering
            Mode::Normal | Mode::Command => {
                let selected_node = state.treeview[state.tree_view_cursor].node.clone();
                match render_main_display(frame, &main_display_area, &selected_node, state) {
                    Ok(()) => {}
                    Err(e) => render_error(frame, &format!("Error: {}", e)),
                }
            }
            Mode::Help | Mode::MultiChart | Mode::Settings => {} // handled above
        }

        // Render command prompt at the bottom of the tree panel
        // (or bottom-left of body when tree is hidden)
        if let Mode::Command = state.mode {
            let cmd_area = tree_area_opt.unwrap_or(body_area);
            render_command_dialog(frame, cmd_area, state);
        }

        render_hint_bar(frame, hint_area, state);
    };

    // First time draw nice state
    terminal.draw(|f| draw_closure(f, &mut state))?;

    handle_term_events(tx_events, state.cfg.ui.poll_interval_ms);

    loop {
        let event = rx_events.recv();
        let event = match event {
            Ok(event) => event,
            Err(error) => {
                log_error(error);
                panic!("Terminal events channel closed unexpectedly.")
            }
        };
        match event {
            AppEvent::TermEvent(event) => {
                match handle_input_event(&mut state, event)? {
                EventResult::Quit => {
                    break;
                }
                EventResult::Continue => {}
                EventResult::Redraw => {
                    terminal.draw(|f| {
                        draw_closure(f, &mut state);
                    })?;
                }
                EventResult::Copying => {
                    state.copying = true;
                    terminal.draw(|f| {
                        draw_closure(f, &mut state);
                    })?;
                    // sleep for 50 ms
                    state.copying = false;
                    thread::sleep(std::time::Duration::from_millis(100));
                    terminal.draw(|f| {
                        draw_closure(f, &mut state);
                    })?;
                }
                EventResult::Error(e) => {
                    terminal.draw(|f| {
                        render_error(f, &e);
                    })?;
                    thread::sleep(std::time::Duration::from_secs(2));
                    terminal.draw(|f| {
                        draw_closure(f, &mut state);
                    })?;
                }
                EventResult::Info(msg) => {
                    terminal.draw(|f| {
                        render_info(f, &msg);
                    })?;
                    thread::sleep(std::time::Duration::from_secs(2));
                    terminal.draw(|f| {
                        draw_closure(f, &mut state);
                    })?;
                }
            }},
            AppEvent::ImageResized(resize_response) => match resize_response {
                ImageResizeResult::Success(resize_response) => {
                    if let Some(ref mut img_thread_protocol) = state.img_state.protocol {
                        let _ = img_thread_protocol.update_resized_protocol(resize_response);
                        terminal.draw(|f| {
                            draw_closure(f, &mut state);
                        })?;
                    }
                }
                ImageResizeResult::Error(e) => {
                    state.img_state.error = Some(format!("Error resizing image: {}", e));
                    terminal.draw(|f| {
                        draw_closure(f, &mut state);
                    })?;
                }
            },
            AppEvent::ImageLoad(img_load) => match img_load {
                ImageLoadedResult::Success(thread_protocol) => {
                    state.img_state.indexes_loaded = state.img_state.indexes_to_load.clone();
                    state.img_state.protocol = Some(thread_protocol);
                    state.img_state.error = None;
                    terminal.draw(|f| {
                        draw_closure(f, &mut state);
                    })?;
                }
                ImageLoadedResult::Failure(f) => {
                    state.img_state.indexes_loaded = state.img_state.indexes_to_load.clone();
                    state.img_state.protocol = None;
                    state.img_state.error = Some(f);
                    terminal.draw(|f| {
                        draw_closure(f, &mut state);
                    })?;
                }
            },
            AppEvent::MultiImageLoad(slot, img_load) => {
                if slot < state.multi_image_siblings.len() {
                    match img_load {
                        ImageLoadedResult::Success(thread_protocol) => {
                            state.multi_image_siblings[slot].protocol = Some(thread_protocol);
                            state.multi_image_siblings[slot].loaded_indexes =
                                state.img_state.indexes_to_load.clone();
                        }
                        ImageLoadedResult::Failure(_) => {
                            state.multi_image_siblings[slot].protocol = None;
                        }
                    }
                    terminal.draw(|f| {
                        draw_closure(f, &mut state);
                    })?;
                }
            },
            AppEvent::Fd5VerifyComplete(status) => {
                state.fd5_status = Some(status);
                terminal.draw(|f| {
                    draw_closure(f, &mut state);
                })?;
            },
        }
    }
    Ok(IntendedMainLoopBreak {})
}

#[allow(clippy::large_enum_variant)]
pub enum AppEvent {
    TermEvent(event::Event),
    ImageResized(ImageResizeResult),
    ImageLoad(ImageLoadedResult),
    MultiImageLoad(usize, ImageLoadedResult),
    Fd5VerifyComplete(fd5::Fd5Status),
}

fn handle_term_events(tx_events: Sender<AppEvent>, poll_ms: u64) {
    thread::spawn(move || loop {
        if event::poll(std::time::Duration::from_millis(poll_ms)).is_ok() {
            if let Ok(event) = event::read() {
                match tx_events.send(AppEvent::TermEvent(event)) {
                    Ok(_) => {}
                    Err(e) => log_error(e),
                }
            }
        }
    });
}

fn render_error(frame: &mut Frame<'_>, error: &str) {
    let error_text = Text::from(error);
    let error_paragraph = Paragraph::new(error_text)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Red))
                .border_type(ratatui::widgets::BorderType::Rounded)
                .title("Error")
                .title_style(Style::default().fg(Color::Yellow).bold())
                .title_alignment(Alignment::Center),
        )
        .wrap(Wrap { trim: true });
    frame.render_widget(error_paragraph, frame.area());
}

fn render_info(frame: &mut Frame<'_>, msg: &str) {
    let info_text = Text::from(msg);
    let info_paragraph = Paragraph::new(info_text)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Green))
                .border_type(ratatui::widgets::BorderType::Rounded)
                .title("Info")
                .title_style(Style::default().fg(Color::Green).bold())
                .title_alignment(Alignment::Center),
        )
        .wrap(Wrap { trim: true });
    frame.render_widget(info_paragraph, frame.area());
}
