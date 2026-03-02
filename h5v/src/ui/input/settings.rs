use ratatui::crossterm::event::{Event, KeyCode, KeyEventKind};

use crate::{
    config::ConfigValue,
    error::AppError,
    ui::hints::KeyHint,
    ui::state::{AppState, Mode},
};

use super::EventResult;

static HINTS: &[KeyHint] = &[
    KeyHint::new("\u{2191}\u{2193}", "Navigate"),
    KeyHint::new("Enter", "Edit"),
    KeyHint::new("S", "Save"),
    KeyHint::new("D", "Default"),
    KeyHint::new("Esc", "Close"),
];

pub fn hints() -> &'static [KeyHint] {
    HINTS
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hints_count() {
        assert_eq!(hints().len(), 5);
    }
}

pub fn handle_settings_event(
    state: &mut AppState<'_>,
    event: Event,
) -> Result<EventResult, AppError> {
    let Event::Key(key_event) = event else {
        if let Event::Resize(_, _) = event {
            return Ok(EventResult::Redraw);
        }
        return Ok(EventResult::Continue);
    };

    if key_event.kind != KeyEventKind::Press {
        return Ok(EventResult::Continue);
    }

    if state.settings_state.editing {
        return handle_editing(state, key_event.code);
    }

    handle_browsing(state, key_event.code)
}

fn handle_browsing(state: &mut AppState<'_>, code: KeyCode) -> Result<EventResult, AppError> {
    let field_count = state.settings_state.fields.len();

    match code {
        KeyCode::Esc | KeyCode::Char('q') => {
            state.mode = Mode::Normal;
            Ok(EventResult::Redraw)
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if state.settings_state.cursor > 0 {
                state.settings_state.cursor -= 1;
            }
            state.settings_state.message = None;
            Ok(EventResult::Redraw)
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if state.settings_state.cursor + 1 < field_count {
                state.settings_state.cursor += 1;
            }
            state.settings_state.message = None;
            Ok(EventResult::Redraw)
        }
        KeyCode::Enter => {
            // Start editing
            let cursor = state.settings_state.cursor;
            if cursor < field_count {
                let (_, ref val) = state.settings_state.fields[cursor];
                state.settings_state.edit_buffer = val.to_display();
                state.settings_state.edit_cursor = state.settings_state.edit_buffer.len();
                state.settings_state.editing = true;
                state.settings_state.message = None;
            }
            Ok(EventResult::Redraw)
        }
        KeyCode::Char('s') | KeyCode::Char('S') => {
            // Save config
            match state.cfg.save() {
                Ok(()) => {
                    state.settings_state.message = Some("Saved!".into());
                }
                Err(e) => {
                    state.settings_state.message = Some(format!("Save failed: {e}"));
                }
            }
            Ok(EventResult::Redraw)
        }
        KeyCode::Char('d') | KeyCode::Char('D') => {
            // Reset selected field to default
            let cursor = state.settings_state.cursor;
            if cursor < field_count {
                let default_val = state.settings_state.fields[cursor].0.default.clone();
                let key = state.settings_state.fields[cursor].0.key;
                match state.cfg.set_field(key, default_val) {
                    Ok(()) => {
                        state.nav_accel.update_from_config(&state.cfg.navigation);
                        state.settings_state.refresh(&state.cfg);
                        state.settings_state.message = Some("Reset to default".into());
                    }
                    Err(e) => {
                        state.settings_state.message = Some(format!("Error: {e}"));
                    }
                }
            }
            Ok(EventResult::Redraw)
        }
        _ => Ok(EventResult::Continue),
    }
}

fn handle_editing(state: &mut AppState<'_>, code: KeyCode) -> Result<EventResult, AppError> {
    match code {
        KeyCode::Esc => {
            // Cancel editing
            state.settings_state.editing = false;
            state.settings_state.message = None;
            Ok(EventResult::Redraw)
        }
        KeyCode::Enter => {
            // Confirm edit
            let cursor = state.settings_state.cursor;
            let buf = state.settings_state.edit_buffer.clone();
            let (ref meta, ref current_val) = state.settings_state.fields[cursor];

            match ConfigValue::parse(current_val, &buf) {
                Ok(new_val) => {
                    if !new_val.in_range(&meta.min, &meta.max) {
                        state.settings_state.message = Some(format!(
                            "Out of range [{} – {}]",
                            meta.min.to_display(),
                            meta.max.to_display()
                        ));
                        return Ok(EventResult::Redraw);
                    }
                    let key = meta.key;
                    let is_cache_key = key == "preload_mb" || key == "max_dataset_mb";
                    match state.cfg.set_field(key, new_val) {
                        Ok(()) => {
                            state.nav_accel.update_from_config(&state.cfg.navigation);
                            state.settings_state.editing = false;
                            state.settings_state.refresh(&state.cfg);
                            if is_cache_key {
                                state.settings_state.message =
                                    Some("Changed (restart needed for cache)".into());
                            } else {
                                state.settings_state.message = None;
                            }
                        }
                        Err(e) => {
                            state.settings_state.message = Some(format!("Error: {e}"));
                        }
                    }
                }
                Err(e) => {
                    state.settings_state.message = Some(format!("Invalid: {e}"));
                }
            }
            Ok(EventResult::Redraw)
        }
        KeyCode::Backspace => {
            let ecur = state.settings_state.edit_cursor;
            if ecur > 0 {
                state.settings_state.edit_buffer.remove(ecur - 1);
                state.settings_state.edit_cursor -= 1;
            }
            Ok(EventResult::Redraw)
        }
        KeyCode::Delete => {
            let ecur = state.settings_state.edit_cursor;
            if ecur < state.settings_state.edit_buffer.len() {
                state.settings_state.edit_buffer.remove(ecur);
            }
            Ok(EventResult::Redraw)
        }
        KeyCode::Left => {
            if state.settings_state.edit_cursor > 0 {
                state.settings_state.edit_cursor -= 1;
            }
            Ok(EventResult::Redraw)
        }
        KeyCode::Right => {
            if state.settings_state.edit_cursor < state.settings_state.edit_buffer.len() {
                state.settings_state.edit_cursor += 1;
            }
            Ok(EventResult::Redraw)
        }
        KeyCode::Home => {
            state.settings_state.edit_cursor = 0;
            Ok(EventResult::Redraw)
        }
        KeyCode::End => {
            state.settings_state.edit_cursor = state.settings_state.edit_buffer.len();
            Ok(EventResult::Redraw)
        }
        KeyCode::Char(c) => {
            let ecur = state.settings_state.edit_cursor;
            state.settings_state.edit_buffer.insert(ecur, c);
            state.settings_state.edit_cursor += 1;
            Ok(EventResult::Redraw)
        }
        _ => Ok(EventResult::Continue),
    }
}
