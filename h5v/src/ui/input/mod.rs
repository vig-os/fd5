use attributes::handle_normal_attributes;
use content::handle_normal_content_event;
use ratatui::crossterm::event::{Event, KeyCode, KeyEventKind, KeyModifiers};
use tree::handle_normal_tree_event;

use crate::{
    error::AppError,
    h5f::Node,
    search::{full_traversal, Searcher},
    ui::hints::KeyHint,
};

use super::state::{AppState, ContentShowMode, Focus, LastFocused, Mode};

pub mod attributes;
pub mod command;
pub mod content;
pub mod mchart;
pub mod search;
pub mod settings;
pub mod tree;

static GLOBAL_HINTS: &[KeyHint] = &[
    KeyHint::new("q", "Quit"),
    KeyHint::new("?", "Help"),
    KeyHint::new("/", "Search"),
    KeyHint::new(":", "Command"),
    KeyHint::new("Tab", "Preview/Matrix"),
    KeyHint::new("\u{21E7}\u{2190}\u{2191}\u{2192}\u{2193}", "Focus"),
    KeyHint::new("^b", "Toggle Tree"),
];

pub fn global_hints() -> &'static [KeyHint] {
    GLOBAL_HINTS
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn global_hints_count() {
        assert_eq!(global_hints().len(), 7);
    }
}

pub enum EventResult {
    Quit,
    Redraw,
    Copying,
    Continue,
    Error(String),
    Info(String),
}

pub fn handle_input_event(state: &mut AppState<'_>, event: Event) -> Result<EventResult, AppError> {
    if let Event::Resize(_, __) = event {
        return Ok(EventResult::Redraw);
    }

    match state.mode {
        Mode::Command => command::handle_command_event(state, event),
        Mode::MultiChart => mchart::handle_mchart_event(state, event),
        Mode::Settings => settings::handle_settings_event(state, event),
        Mode::Normal => {
            if let Event::Key(key_event) = event {
                // Unified 3D+ arrow navigation for both preview and matrix
                if matches!(state.focus, Focus::Content) && key_event.modifiers.is_empty() {
                    let is_ndim3 = {
                        let node = state.treeview[state.tree_view_cursor].node.borrow();
                        match (&node.node, state.content_mode) {
                            (Node::Dataset(_, dsattr), ContentShowMode::Preview) => {
                                dsattr.image.is_some() && dsattr.shape.len() >= 3
                            }
                            (Node::Dataset(_, dsattr), ContentShowMode::Matrix) => {
                                dsattr.shape.len() >= 3
                            }
                            _ => false,
                        }
                    };
                    if is_ndim3 {
                        match (key_event.code, key_event.kind) {
                            (KeyCode::Up | KeyCode::Down, KeyEventKind::Press) => {
                                let dim_size = state.current_dim_size();
                                let direction: isize = if key_event.code == KeyCode::Up { -1 } else { 1 };
                                let n = state.nav_accel.on_press(key_event.code, dim_size);
                                state.dim_navigate(direction, n)?;
                                // In preview mode on a stepping dim, load image immediately
                                if state.content_mode == ContentShowMode::Preview
                                    && state.is_stepping_dim()
                                {
                                    return state.send_image_load();
                                }
                                return Ok(EventResult::Redraw);
                            }
                            (KeyCode::Up | KeyCode::Down, KeyEventKind::Repeat) => {
                                let dim_size = state.current_dim_size();
                                let direction: isize = if key_event.code == KeyCode::Up { -1 } else { 1 };
                                let origin = state.current_position();
                                let target = state.nav_accel.on_repeat(origin, direction, dim_size);
                                // Numbers update each frame, but NO image load during hold
                                if target == origin {
                                    return Ok(EventResult::Continue);
                                }
                                return state.dim_set_to(target);
                            }
                            (KeyCode::Up | KeyCode::Down, KeyEventKind::Release) => {
                                // After hold ends, load image at final position
                                if state.nav_accel.on_release()
                                    && state.content_mode == ContentShowMode::Preview
                                    && state.is_stepping_dim()
                                {
                                    return state.send_image_load();
                                }
                                return Ok(EventResult::Continue);
                            }
                            (KeyCode::Left, KeyEventKind::Press) => return state.image_move_dim(-1),
                            (KeyCode::Right, KeyEventKind::Press) => return state.image_move_dim(1),
                            (KeyCode::Enter, KeyEventKind::Press) => return state.image_assign_dim(),
                            _ => {} // fall through
                        }
                    }
                }
                match (key_event.code, key_event.modifiers) {
                    (KeyCode::Char(':'), _) => {
                        state.mode = Mode::Command;
                        state.command_state.command_buffer.clear();
                        state.command_state.cursor = 0;
                        Ok(EventResult::Redraw)
                    }
                    (KeyCode::Char('.'), _) => state.reexecute_command(),
                    (KeyCode::Char('/'), _) => {
                        if state.searcher.is_none() {
                            let Node::File(ref file) = state.root.borrow().node else {
                                return Ok(EventResult::Error(
                                    "Search only available for HDF5 files".to_string(),
                                ));
                            };
                            let Ok(file_as_group) = file.as_group() else {
                                return Ok(EventResult::Error(
                                    "Search only available for HDF5 files with roots that can polymorp as group.".to_string(),
                                ));
                            };
                            let all_h5_paths = full_traversal(&file_as_group);
                            state.searcher = Some(Searcher::new(all_h5_paths));
                        }
                        let Some(ref mut searcher) = state.searcher else {
                            return Ok(EventResult::Error("Search not available".to_string()));
                        };
                        searcher.query.clear();
                        searcher.line_cursor = 0;
                        state.mode = Mode::Search;
                        Ok(EventResult::Redraw)
                    }
                    (KeyCode::Char('q'), _) => Ok(EventResult::Quit),
                    (KeyCode::Char('c'), KeyModifiers::CONTROL) => Ok(EventResult::Quit),
                    (KeyCode::Tab, _) => {
                        let available = state.treeview[state.tree_view_cursor]
                            .node
                            .borrow_mut()
                            .content_show_modes();
                        state.swap_content_show_mode(available);
                        Ok(EventResult::Redraw)
                    }
                    (KeyCode::Char('?'), _) => {
                        state.mode = Mode::Help;
                        Ok(EventResult::Redraw)
                    }
                    (KeyCode::Char('M'), _) => {
                        state.mode = Mode::MultiChart;
                        Ok(EventResult::Redraw)
                    }
                    (KeyCode::Right, KeyModifiers::SHIFT) => {
                        if let Focus::Tree(LastFocused::Attributes) = state.focus {
                            state.focus = Focus::Attributes;
                        }
                        if let Focus::Tree(LastFocused::Content) = state.focus {
                            state.focus = Focus::Content;
                        }
                        Ok(EventResult::Redraw)
                    }
                    (KeyCode::Left, KeyModifiers::SHIFT) => {
                        if let Focus::Attributes = state.focus {
                            state.focus = Focus::Tree(LastFocused::Attributes);
                        }
                        if let Focus::Content = state.focus {
                            state.focus = Focus::Tree(LastFocused::Content);
                        }
                        Ok(EventResult::Redraw)
                    }
                    (KeyCode::Down, KeyModifiers::SHIFT) => {
                        if let Focus::Attributes = state.focus {
                            state.focus = Focus::Content;
                        }
                        Ok(EventResult::Redraw)
                    }

                    (KeyCode::Up, KeyModifiers::SHIFT) => {
                        if let Focus::Content = state.focus {
                            state.focus = Focus::Attributes;
                        }
                        Ok(EventResult::Redraw)
                    }
                    (KeyCode::Char('b'), KeyModifiers::CONTROL) => {
                        state.show_tree_view = !state.show_tree_view;
                        if state.show_tree_view {
                            state.focus = Focus::Tree(LastFocused::Content);
                        } else {
                            state.focus = Focus::Content;
                        }

                        Ok(EventResult::Redraw)
                    }
                    (KeyCode::Char('x'), _) => state.change_x(1),
                    (KeyCode::Char('X'), _) => state.change_x(-1),
                    (KeyCode::Char('r'), _) => state.change_row(1),
                    (KeyCode::Char('R'), _) => state.change_row(-1),
                    (KeyCode::Char('c'), _) => state.change_col(1),
                    (KeyCode::Char('C'), _) => state.change_col(-1),
                    (KeyCode::Up, KeyModifiers::ALT) => state.change_selected_index(-1),
                    (KeyCode::Down, KeyModifiers::ALT) => state.change_selected_index(1),
                    (KeyCode::PageUp, KeyModifiers::ALT) => state.change_selected_index(-10),
                    (KeyCode::PageDown, KeyModifiers::ALT) => state.change_selected_index(10),
                    (KeyCode::Left, KeyModifiers::ALT) => state.change_selected_dimension(-1),
                    (KeyCode::Right, KeyModifiers::ALT) => state.change_selected_dimension(1),
                    (KeyCode::Up, KeyModifiers::CONTROL) => state.up(1),
                    (KeyCode::Down, KeyModifiers::CONTROL) => state.down(1),
                    (KeyCode::Right, KeyModifiers::CONTROL) => state.right(1),
                    (KeyCode::Left, KeyModifiers::CONTROL) => state.left(1),
                    (KeyCode::PageDown, _) => {
                        if state.content_mode == ContentShowMode::Matrix {
                            let page = state.matrix_view_state.rows_currently_available.max(1);
                            state.down(page)
                        } else {
                            state.down(20)
                        }
                    }
                    (KeyCode::PageUp, _) => {
                        if state.content_mode == ContentShowMode::Matrix {
                            let page = state.matrix_view_state.rows_currently_available.max(1);
                            state.up(page)
                        } else {
                            state.up(20)
                        }
                    }
                    (KeyCode::Home, _) => {
                        if state.content_mode == ContentShowMode::Matrix {
                            state.set(0)
                        } else {
                            Ok(EventResult::Continue)
                        }
                    }
                    (KeyCode::End, _) => {
                        if state.content_mode == ContentShowMode::Matrix {
                            state.set(usize::MAX)
                        } else {
                            Ok(EventResult::Continue)
                        }
                    }
                    _ => match state.focus {
                        Focus::Tree(_) => handle_normal_tree_event(state, event),
                        Focus::Attributes => handle_normal_attributes(state, event),
                        Focus::Content => handle_normal_content_event(state, event),
                    },
                }
            } else {
                Ok(EventResult::Continue)
            }
        }
        Mode::Search => {
            if let Event::Key(key_event) = event {
                match key_event.code {
                    KeyCode::Char('q') => return Ok(EventResult::Quit),
                    KeyCode::Esc => {
                        state.mode = Mode::Normal;
                        return Ok(EventResult::Redraw);
                    }
                    _ => {}
                }
            }
            search::handle_search_event(state, event)
        }
        Mode::Help => {
            if let Event::Key(key_event) = event {
                if key_event.code == KeyCode::Esc {
                    state.mode = Mode::Normal;
                    return Ok(EventResult::Redraw);
                }
            }
            Ok(EventResult::Continue)
        }
    }
}
