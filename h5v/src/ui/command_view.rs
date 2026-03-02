use ratatui::{
    layout::{Position, Rect},
    style::{Color, Style},
    Frame,
};

use super::state::AppState;

/// Render a vim-style command prompt at the bottom of `area`.
/// `area` is typically the tree panel rect (or body_area when tree is hidden).
pub fn render_command_dialog(f: &mut Frame, area: Rect, state: &mut AppState) {
    if area.height == 0 || area.width < 4 {
        return;
    }

    let prompt_y = area.y + area.height - 1;
    let prompt_area = Rect {
        x: area.x,
        y: prompt_y,
        width: area.width,
        height: 1,
    };

    let prefix = ":";
    let buf = &state.command_state.command_buffer;
    let text = format!("{prefix}{buf}");
    // Pad to fill the row so the background covers the whole line
    let text = format!("{text:<width$}", width = prompt_area.width as usize);

    let style = Style::default().fg(Color::White).bg(Color::DarkGray);
    let widget = ratatui::widgets::Paragraph::new(text).style(style);
    f.render_widget(widget, prompt_area);

    let cursor_x = area.x + prefix.len() as u16 + state.command_state.cursor as u16;
    f.set_cursor_position(Position::new(cursor_x, prompt_y));
}
