use ratatui::crossterm::event::{Event, KeyCode, KeyEventKind};

use crate::{error::AppError, ui::hints::KeyHint, ui::state::{AppState, ChartMode}};

use super::EventResult;

static HINTS: &[KeyHint] = &[
    KeyHint::new("PgUp/Dn", "Scroll"),
    KeyHint::new("h", "Histogram"),
    KeyHint::new("l/L", "Log Y/X"),
];

static HINTS_3D: &[KeyHint] = &[
    KeyHint::new("\u{2191}", "Step\u{2212}"),
    KeyHint::new("\u{2193}", "Step+"),
    KeyHint::new("\u{2191}\u{2191}", "5% Jump"),
    KeyHint::new("\u{2191}\u{2191}\u{2191}", "Home/End"),
    KeyHint::new("Hold", "Sweep"),
    KeyHint::new("\u{2190}\u{2192}", "Dim"),
    KeyHint::new("Enter", "Assign"),
    KeyHint::new("m", "Multi"),
];

pub fn hints() -> &'static [KeyHint] {
    HINTS
}

pub fn hints_3d() -> &'static [KeyHint] {
    HINTS_3D
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hints_count() {
        assert_eq!(hints().len(), 3);
    }

    #[test]
    fn hints_3d_count() {
        assert_eq!(hints_3d().len(), 8);
    }
}

pub fn handle_normal_content_event(
    state: &mut AppState<'_>,
    event: Event,
) -> Result<EventResult, AppError> {
    match event {
        Event::Key(key_event) => match key_event.kind {
            KeyEventKind::Press => match (key_event.code, key_event.modifiers) {
                (KeyCode::Up, _) => {
                    // Get the current tree item and its attributes
                    Ok(EventResult::Continue)
                }
                (KeyCode::Down, _) => {
                    // Get the current tree item and its attributes
                    Ok(EventResult::Continue)
                }
                (KeyCode::Char('h'), _) => {
                    state.chart_mode = match state.chart_mode {
                        ChartMode::Line => ChartMode::Histogram,
                        ChartMode::Histogram => ChartMode::Line,
                    };
                    Ok(EventResult::Redraw)
                }
                (KeyCode::Char('l'), _) => {
                    state.chart_log_y = !state.chart_log_y;
                    Ok(EventResult::Redraw)
                }
                (KeyCode::Char('L'), _) => {
                    state.chart_log_x = !state.chart_log_x;
                    Ok(EventResult::Redraw)
                }
                (KeyCode::Char('+'), _) => {
                    // Widen window (more contrast range)
                    let w = state.window_width.unwrap_or(4095.0);
                    state.window_width = Some((w * 1.1).min(65535.0));
                    state.auto_window = false;
                    if state.window_center.is_none() {
                        state.window_center = Some(2047.0);
                    }
                    state.img_state.ds = None; // force reload
                    Ok(EventResult::Redraw)
                }
                (KeyCode::Char('-'), _) => {
                    // Narrow window (less contrast range)
                    let w = state.window_width.unwrap_or(4095.0);
                    state.window_width = Some((w / 1.1).max(1.0));
                    state.auto_window = false;
                    if state.window_center.is_none() {
                        state.window_center = Some(2047.0);
                    }
                    state.img_state.ds = None; // force reload
                    Ok(EventResult::Redraw)
                }
                (KeyCode::Char('w'), _) => {
                    // Adjust window center up
                    let c = state.window_center.unwrap_or(2047.0);
                    let step = state.window_width.unwrap_or(4095.0) * 0.05;
                    state.window_center = Some(c + step);
                    state.auto_window = false;
                    if state.window_width.is_none() {
                        state.window_width = Some(4095.0);
                    }
                    state.img_state.ds = None; // force reload
                    Ok(EventResult::Redraw)
                }
                (KeyCode::Char('W'), _) => {
                    // Adjust window center down
                    let c = state.window_center.unwrap_or(2047.0);
                    let step = state.window_width.unwrap_or(4095.0) * 0.05;
                    state.window_center = Some((c - step).max(0.0));
                    state.auto_window = false;
                    if state.window_width.is_none() {
                        state.window_width = Some(4095.0);
                    }
                    state.img_state.ds = None; // force reload
                    Ok(EventResult::Redraw)
                }
                (KeyCode::Char('a'), _) => {
                    // Reset to auto window
                    state.auto_window = true;
                    state.window_center = None;
                    state.window_width = None;
                    state.img_state.ds = None; // force reload
                    Ok(EventResult::Redraw)
                }
                (KeyCode::Char('m'), _) => {
                    // Toggle multi-image mode
                    if state.multi_image_mode {
                        state.multi_image_mode = false;
                        state.multi_image_siblings.clear();
                    } else {
                        let siblings = state.find_image_siblings();
                        if !siblings.is_empty() {
                            state.multi_image_mode = true;
                            state.multi_image_siblings = siblings
                                .into_iter()
                                .map(|(path, filename, img_type)| {
                                    crate::ui::state::MultiImageSlot {
                                        ds_path: path,
                                        filename,
                                        img_type,
                                        protocol: None,
                                        loaded_indexes: vec![],
                                        tx_load: None,
                                    }
                                })
                                .collect();
                            // Force reload to trigger multi-image load
                            state.img_state.ds = None;
                        }
                    }
                    Ok(EventResult::Redraw)
                }
                _ => Ok(EventResult::Continue),
            },
            KeyEventKind::Repeat => Ok(EventResult::Continue),
            KeyEventKind::Release => Ok(EventResult::Continue),
        },
        Event::Resize(_, _) => Ok(EventResult::Redraw),
        _ => Ok(EventResult::Continue),
    }
}
