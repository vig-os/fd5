use std::rc::Rc;

use ratatui::{
    layout::{Alignment, Constraint, Layout, Margin, Offset, Rect},
    style::{Color, Style, Stylize},
    text::{Line, Span},
    widgets::{Block, Borders, Scrollbar, ScrollbarState},
    Frame,
};

use crate::{
    color_consts::{self, BG_COLOR, FOCUS_BG_COLOR},
    h5f::{H5FNode, Node},
};

use super::state::{AppState, AttributeViewSelection, Focus, Mode};

fn make_panels_rect(area: Rect, min_first_panel: u16) -> Rc<[Rect]> {

    Layout::default()
        .direction(ratatui::layout::Direction::Horizontal)
        .constraints([
            Constraint::Length(min_first_panel + 3),
            Constraint::Fill(u16::MAX),
        ])
        .split(area)
}

fn make_panels_scroll(area: Rect, scroll_size: u16) -> Rc<[Rect]> {

    Layout::default()
        .direction(ratatui::layout::Direction::Horizontal)
        .constraints([Constraint::Max(u16::MAX), Constraint::Length(scroll_size)])
        .split(area)
}

fn render_text_overflow_handled(f: &mut Frame, area: &Rect, line: &Line) {
    let line_width = line.width();
    if line_width < (area.width as usize) {
        f.render_widget(line, *area);
    } else {
        let areas =
            Layout::horizontal([Constraint::Fill(u16::MAX), Constraint::Length(1)]).split(*area);
        f.render_widget(line, areas[0]);
        f.render_widget("_", areas[1]);
    }
}

pub fn render_info_attributes(
    f: &mut Frame,
    area: &Rect,
    node: &mut H5FNode,
    state: &mut AppState,
) -> Result<(), hdf5_metno::Error> {
    let bg = match (&state.focus, &state.mode) {
        (Focus::Attributes, Mode::Normal) => FOCUS_BG_COLOR,
        _ => BG_COLOR,
    };

    let attr_header_block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Green))
        .border_type(ratatui::widgets::BorderType::Rounded)
        .title("Attributes".to_string())
        .bg(bg)
        .title_style(Style::default().fg(Color::Yellow).bold())
        .title_alignment(Alignment::Center);
    f.render_widget(attr_header_block, *area);

    let area_inner = area.inner(Margin {
        horizontal: 2,
        vertical: 1,
    });

    // Extract ds_path and is_root before read_attributes to avoid borrow conflict
    let ds_path = match &node.node {
        Node::Dataset(_, meta) => Some(meta.full_path.clone()),
        _ => None,
    };
    let is_root = matches!(&node.node, Node::File(_));

    let attributes = node.read_attributes()?;

    // Inject dataset stats from preload cache if available
    let stats_line: Option<(Line<'static>, Line<'static>)> = ds_path.and_then(|path| {
        state.preload_cache.lock().ok().and_then(|guard| {
            guard.get_stats(&path).map(|stats| {
                let name = ratatui::text::Span::styled(
                    "stats",
                    Style::default()
                        .fg(color_consts::VARIABLE_BLUE_BUILTIN)
                        .bold(),
                );
                let name_area_width = attributes.longest_name_length.max(5) + 3;
                let extra = name_area_width as usize - "stats".len();
                let helper = ratatui::text::Span::styled(
                    "─".repeat(extra.saturating_sub(1)),
                    Style::default().fg(color_consts::LINES_COLOR),
                );
                let eq = ratatui::text::Span::styled(
                    "=",
                    Style::default().fg(color_consts::EQUAL_SIGN_COLOR),
                );
                let name_line = Line::from(vec![name, helper, eq]);
                let value = ratatui::text::Span::styled(
                    stats.display_string(),
                    Style::default()
                        .fg(color_consts::BUILT_IN_VALUE_COLOR)
                        .bold(),
                );
                let value_line = Line::from(vec![value]);
                (name_line, value_line)
            })
        })
    });

    // Build fd5 status line for root node
    let fd5_line: Option<(Line<'static>, Line<'static>)> = if is_root {
        state.fd5_status.as_ref().map(|status| {
            let name = Span::styled(
                "fd5",
                Style::default()
                    .fg(color_consts::VARIABLE_BLUE_BUILTIN)
                    .bold(),
            );
            let name_area_width = attributes.longest_name_length.max(5) + 3;
            let extra = name_area_width as usize - "fd5".len();
            let helper = Span::styled(
                "\u{2500}".repeat(extra.saturating_sub(1)),
                Style::default().fg(color_consts::LINES_COLOR),
            );
            let eq = Span::styled(
                "=",
                Style::default().fg(color_consts::EQUAL_SIGN_COLOR),
            );
            let name_line = Line::from(vec![name, helper, eq]);
            let (label, color) = match status {
                fd5::Fd5Status::Checking => ("checking...", Color::Yellow),
                fd5::Fd5Status::Valid(_) => ("valid", Color::Green),
                fd5::Fd5Status::Invalid { .. } => ("INVALID", Color::Red),
                fd5::Fd5Status::NotFd5 => ("not fd5", Color::DarkGray),
                fd5::Fd5Status::Error(_) => ("error", Color::Red),
            };
            let value = Span::styled(
                label.to_string(),
                Style::default().fg(color).bold(),
            );
            let value_line = Line::from(vec![value]);
            (name_line, value_line)
        })
    } else {
        None
    };

    // Build the full attribute list, including stats and fd5 status if available
    let mut all_rendered: Vec<&(Line<'static>, Line<'static>)> =
        attributes.rendered_attributes.iter().collect();
    if let Some(ref stats) = stats_line {
        all_rendered.push(stats);
    }
    if let Some(ref fd5) = fd5_line {
        all_rendered.push(fd5);
    }

    let min_first_panel = match attributes.longest_name_length {
        0..5 => 5,
        5..=u16::MAX => attributes.longest_name_length,
    };
    let scroll_size = if area_inner.height as usize >= all_rendered.len() {
        0
    } else {
        3
    };
    let area = make_panels_rect(area_inner, min_first_panel);
    let [name_area, value_area] = area.as_ref() else {
        panic!("Could not get the areas for the info attribute panels");
    };

    let value_scroll_areas = make_panels_scroll(*value_area, scroll_size);
    let [value_area, scroll_area] = value_scroll_areas.as_ref() else {
        panic!("Could not get the areas for scroll panels.");
    };
    let height = name_area.height as i32;
    let heightu = height as usize;

    if scroll_area.height > 0 && scroll_area.width > 0 {
        let scrollbar = Scrollbar::new(ratatui::widgets::ScrollbarOrientation::VerticalRight)
            .end_symbol(Some("v"))
            .thumb_symbol("█")
            .begin_symbol(Some("^"));
        let mut scrollbar_state = ScrollbarState::new(all_rendered.len())
            .viewport_content_length(height as usize)
            .position(state.attributes_view_cursor.attribute_index);
        f.render_stateful_widget(scrollbar, *scroll_area, &mut scrollbar_state);
    }

    let mut offset = 0;

    let highlighted_index = &state
        .attributes_view_cursor
        .attribute_index
        .saturating_sub(state.attributes_view_cursor.attribute_offset)
        .clamp(0, heightu.saturating_sub(1));

    let highlighted_bg_color = if state.copying {
        color_consts::HIGHLIGHT_BG_COLOR_COPY
    } else {
        color_consts::HIGHLIGHT_BG_COLOR
    };

    let new_attr_offset = if state.attributes_view_cursor.attribute_index
        > heightu
            .saturating_sub(1)
            .saturating_add(state.attributes_view_cursor.attribute_offset)
    {
        state
            .attributes_view_cursor
            .attribute_index
            .saturating_sub(height.saturating_sub(1) as usize)
    } else if state.attributes_view_cursor.attribute_index
        <= state.attributes_view_cursor.attribute_offset
    {
        state.attributes_view_cursor.attribute_index
    } else {
        state.attributes_view_cursor.attribute_offset
    };
    state.attributes_view_cursor.attribute_offset = new_attr_offset;
    let mut attributes_to_skip = new_attr_offset;

    #[allow(clippy::explicit_counter_loop)]
    for (name_line, value_line) in &all_rendered {
        if attributes_to_skip != 0 {
            attributes_to_skip -= 1;
            continue;
        }
        if offset == *highlighted_index as i32 {
            match state.attributes_view_cursor.attribute_view_selection {
                AttributeViewSelection::Name => {
                    f.render_widget(
                        name_line.clone().bg(highlighted_bg_color),
                        name_area.offset(Offset { x: 0, y: offset }),
                    );

                    render_text_overflow_handled(
                        f,
                        &value_area.offset(Offset { x: 1, y: offset }),
                        value_line,
                    );
                }
                AttributeViewSelection::Value => {
                    f.render_widget(name_line, name_area.offset(Offset { x: 0, y: offset }));
                    render_text_overflow_handled(
                        f,
                        &value_area.offset(Offset { x: 1, y: offset }),
                        &value_line.clone().bg(highlighted_bg_color),
                    );
                }
            }
        } else {
            f.render_widget(name_line, name_area.offset(Offset { x: 0, y: offset }));
            render_text_overflow_handled(
                f,
                &value_area.offset(Offset { x: 1, y: offset }),
                value_line,
            );
        }

        if offset >= height - 1 {
            break;
        }
        offset += 1;
    }

    Ok(())
}
