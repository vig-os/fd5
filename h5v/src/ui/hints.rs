use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    Frame,
};

use super::input;
use super::state::{AppState, ContentShowMode, Focus, Mode};

/// A single key hint: what to press and what it does.
pub struct KeyHint {
    pub key: &'static str,
    pub action: &'static str,
}

impl KeyHint {
    pub const fn new(key: &'static str, action: &'static str) -> Self {
        Self { key, action }
    }
}

/// Collect the hints applicable to the current state.
pub fn hints_for_state(state: &AppState) -> Vec<&'static [KeyHint]> {
    let mut groups = Vec::new();

    match state.mode {
        Mode::Command => groups.push(input::command::hints()),
        Mode::Search => groups.push(input::search::hints()),
        Mode::Help => groups.push(HELP_HINTS),
        Mode::Settings => groups.push(input::settings::hints()),
        Mode::MultiChart => groups.push(input::mchart::hints()),
        Mode::Normal => {
            groups.push(input::global_hints());

            match state.focus {
                Focus::Tree(_) => groups.push(input::tree::hints()),
                Focus::Attributes => groups.push(input::attributes::hints()),
                Focus::Content => {
                    let is_3d = {
                        let node = state.treeview[state.tree_view_cursor].node.borrow();
                        match (&node.node, state.content_mode) {
                            (crate::h5f::Node::Dataset(_, dsattr), ContentShowMode::Preview) => {
                                dsattr.image.is_some() && dsattr.shape.len() >= 3
                            }
                            (crate::h5f::Node::Dataset(_, dsattr), ContentShowMode::Matrix) => {
                                dsattr.shape.len() >= 3
                            }
                            _ => false,
                        }
                    };
                    if is_3d {
                        groups.push(input::content::hints_3d());
                    } else {
                        groups.push(input::content::hints());
                    }
                }
            }
        }
    }

    groups
}

/// Compute how many rows the hint bar needs for a given terminal width.
/// Returns at least 1, capped at `max_rows`.
pub fn hint_rows_needed(state: &AppState, width: u16, max_rows: u16) -> u16 {
    let groups = hints_for_state(state);
    let padding = 2u16;
    let sep_width = 2u16;
    let mut rows = 1u16;
    let mut line_width = padding;
    let mut first_on_line = true;

    for group in &groups {
        for hint in *group {
            let key_text = format!(" {} ", hint.key);
            let action_text = format!(" {}", hint.action);
            let entry_width = key_text.chars().count() as u16 + action_text.chars().count() as u16;
            let needed = if first_on_line { entry_width } else { sep_width + entry_width };

            if !first_on_line && line_width + needed > width {
                rows += 1;
                if rows >= max_rows {
                    return max_rows;
                }
                line_width = padding + entry_width;
                first_on_line = false;
            } else {
                line_width += needed;
                first_on_line = false;
            }
        }
    }
    rows.max(1)
}

/// Render the hint bar in the given area.
/// Uses multiple rows if hints don't fit in the available width.
pub fn render_hint_bar(frame: &mut Frame, area: Rect, state: &AppState) {
    let groups = hints_for_state(state);

    let key_style = Style::default()
        .fg(Color::Black)
        .bg(Color::DarkGray)
        .add_modifier(Modifier::BOLD);
    let action_style = Style::default().fg(Color::Gray);
    let sep_style = Style::default().fg(Color::DarkGray);

    // Collect all hint spans with their widths
    let mut entries: Vec<(String, &'static str)> = Vec::new();
    for group in &groups {
        for hint in *group {
            entries.push((format!(" {} ", hint.key), hint.action));
        }
    }

    let padding = 2u16; // left margin
    let sep_width = 2u16; // "  " between hints
    let max_width = area.width;
    let max_rows = area.height as usize;

    // Break entries into lines that fit within max_width
    let mut lines: Vec<Line> = Vec::new();
    let mut spans: Vec<Span> = Vec::new();
    let mut line_width = padding;
    spans.push(Span::raw("  ")); // left padding

    for (i, (key_text, action)) in entries.iter().enumerate() {
        let action_text = format!(" {action}");
        // Unicode-aware width estimate: count chars (good enough for our symbols)
        let entry_width = key_text.chars().count() as u16 + action_text.chars().count() as u16;
        let needed = if i > 0 && !spans.is_empty() && spans.len() > 1 {
            sep_width + entry_width
        } else {
            entry_width
        };

        if line_width + needed > max_width && spans.len() > 1 {
            // Wrap to next line
            lines.push(Line::from(std::mem::take(&mut spans)));
            if lines.len() >= max_rows {
                break;
            }
            spans.push(Span::raw("  ")); // left padding for new line
            line_width = padding;
        }

        if spans.len() > 1 {
            spans.push(Span::styled("  ", sep_style));
            line_width += sep_width;
        }
        spans.push(Span::styled(key_text.clone(), key_style));
        spans.push(Span::styled(action_text, action_style));
        line_width += entry_width;
    }
    if spans.len() > 1 && lines.len() < max_rows {
        lines.push(Line::from(spans));
    }

    // Render each line into its own row
    for (i, line) in lines.into_iter().enumerate() {
        if (i as u16) >= area.height {
            break;
        }
        let row = Rect {
            x: area.x,
            y: area.y + i as u16,
            width: area.width,
            height: 1,
        };
        frame.render_widget(line, row);
    }
}

// ── Hint tables ────────────────────────────────────────────
// Most hints live next to their keybindings in the input modules.
// Help mode has no input module, so its hints stay here.

static HELP_HINTS: &[KeyHint] = &[KeyHint::new("Esc", "Close")];

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_helpers::make_test_state;

    #[test]
    fn hints_command_mode() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        state.mode = Mode::Command;
        let groups = hints_for_state(&state);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 9);
    }

    #[test]
    fn hints_search_mode() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        state.mode = Mode::Search;
        let groups = hints_for_state(&state);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 3);
    }

    #[test]
    fn hints_help_mode() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        state.mode = Mode::Help;
        let groups = hints_for_state(&state);
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].len(), 1);
    }

    #[test]
    fn hints_normal_tree() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        state.mode = Mode::Normal;
        state.focus = Focus::Tree(super::super::state::LastFocused::Attributes);
        let groups = hints_for_state(&state);
        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0].len(), 7); // global
        assert_eq!(groups[1].len(), 5); // tree
    }

    #[test]
    fn hints_normal_attrs() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        state.mode = Mode::Normal;
        state.focus = Focus::Attributes;
        let groups = hints_for_state(&state);
        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0].len(), 7); // global
        assert_eq!(groups[1].len(), 3); // attributes
    }

    #[test]
    fn hints_normal_content_2d() {
        let Some(mut state) = make_test_state(&[5, 10]) else {
            eprintln!("Skipping: test setup failed");
            return;
        };
        state.mode = Mode::Normal;
        state.focus = Focus::Content;
        let groups = hints_for_state(&state);
        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0].len(), 7); // global
        assert_eq!(groups[1].len(), 3); // content (2D, non-3D): PgUp/Dn, h, l/L
    }
}
