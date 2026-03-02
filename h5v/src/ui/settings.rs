use ratatui::{
    layout::{Alignment, Constraint, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
    Frame,
};

use super::state::AppState;

pub fn render_settings(frame: &mut Frame, state: &mut AppState) {
    let fields = &state.settings_state.fields;
    let cursor = state.settings_state.cursor;
    let editing = state.settings_state.editing;

    let area = frame.area();
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::LightGreen))
        .border_type(ratatui::widgets::BorderType::Rounded)
        .title(" Settings (S save, D default, Esc close) ")
        .title_style(Style::default().fg(Color::Yellow).bold())
        .title_alignment(Alignment::Center);

    let inner = block.inner(area);
    frame.render_widget(block, area);

    // Reserve bottom 2 lines for status info
    let chunks = Layout::default()
        .direction(ratatui::layout::Direction::Vertical)
        .constraints([Constraint::Min(1), Constraint::Length(2)])
        .split(inner);

    let list_area = chunks[0];
    let status_area = chunks[1];

    // Build lines
    let mut lines: Vec<Line> = Vec::new();
    let mut last_section = "";

    // Compute column widths
    let key_width = fields
        .iter()
        .map(|(meta, _)| meta.key.len())
        .max()
        .unwrap_or(20);
    let val_width = 12;

    for (i, (meta, current_val)) in fields.iter().enumerate() {
        // Section header
        if meta.section != last_section {
            if !last_section.is_empty() {
                lines.push(Line::from(""));
            }
            lines.push(Line::from(vec![
                Span::styled("  [", Style::default().fg(Color::DarkGray)),
                Span::styled(
                    meta.section,
                    Style::default()
                        .fg(Color::Cyan)
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled("]", Style::default().fg(Color::DarkGray)),
            ]));
            last_section = meta.section;
        }

        let is_selected = i == cursor;
        let marker = if is_selected { "► " } else { "  " };
        let marker_style = if is_selected {
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(Color::DarkGray)
        };

        let key_str = format!("{:<width$}", meta.key, width = key_width);
        let key_style = if is_selected {
            Style::default().fg(Color::White)
        } else {
            Style::default().fg(Color::Gray)
        };

        let val_str = if is_selected && editing {
            let buf = &state.settings_state.edit_buffer;
            let ecur = state.settings_state.edit_cursor;
            // Show edit buffer with cursor indicator
            let before = &buf[..ecur.min(buf.len())];
            let cursor_char = buf.chars().nth(ecur).unwrap_or(' ');
            let after = if ecur < buf.len() {
                &buf[ecur + cursor_char.len_utf8()..]
            } else {
                ""
            };
            format!(
                "{before}{cursor_ch}{after}",
                cursor_ch = if ecur < buf.len() {
                    cursor_char
                } else {
                    '▏'
                }
            )
        } else {
            current_val.to_display()
        };
        let val_display = format!("{:<width$}", val_str, width = val_width);

        let val_style = if is_selected && editing {
            Style::default()
                .fg(Color::Black)
                .bg(Color::Yellow)
                .add_modifier(Modifier::BOLD)
        } else if is_selected {
            Style::default()
                .fg(Color::Green)
                .add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(Color::Green)
        };

        let desc_style = Style::default().fg(Color::DarkGray);

        lines.push(Line::from(vec![
            Span::styled(format!("  {marker}"), marker_style),
            Span::styled(key_str, key_style),
            Span::raw("  "),
            Span::styled(val_display, val_style),
            Span::raw("  "),
            Span::styled(meta.description, desc_style),
        ]));
    }

    // Scroll: if cursor line is beyond the visible area, offset
    let visible = list_area.height as usize;
    // Find which line index corresponds to cursor field
    let cursor_line = find_cursor_line(&fields, cursor);
    let scroll_offset = if cursor_line >= visible {
        cursor_line.saturating_sub(visible / 2)
    } else {
        0
    };

    let para = Paragraph::new(lines).scroll((scroll_offset as u16, 0));
    frame.render_widget(para, list_area);

    // Status line: show default + range for selected field
    let mut status_lines = Vec::new();
    if let Some(msg) = &state.settings_state.message {
        status_lines.push(Line::from(vec![Span::styled(
            format!("  {msg}"),
            Style::default().fg(Color::Yellow),
        )]));
    }
    if cursor < fields.len() {
        let (meta, _) = &fields[cursor];
        status_lines.push(Line::from(vec![
            Span::styled("  default: ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                meta.default.to_display(),
                Style::default().fg(Color::White),
            ),
            Span::styled("  range: [", Style::default().fg(Color::DarkGray)),
            Span::styled(meta.min.to_display(), Style::default().fg(Color::White)),
            Span::styled(" – ", Style::default().fg(Color::DarkGray)),
            Span::styled(meta.max.to_display(), Style::default().fg(Color::White)),
            Span::styled("]", Style::default().fg(Color::DarkGray)),
        ]));
    }

    let status_para = Paragraph::new(status_lines);
    frame.render_widget(status_para, status_area);
}

fn find_cursor_line(fields: &[(crate::config::FieldMeta, crate::config::ConfigValue)], cursor: usize) -> usize {
    let mut line = 0;
    let mut last_section = "";
    for (i, (meta, _)) in fields.iter().enumerate() {
        if meta.section != last_section {
            if !last_section.is_empty() {
                line += 1; // empty separator
            }
            line += 1; // section header
            last_section = meta.section;
        }
        if i == cursor {
            return line;
        }
        line += 1;
    }
    line
}
