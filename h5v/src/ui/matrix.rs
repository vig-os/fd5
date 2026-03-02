use std::fmt::Display;

use hdf5_metno::H5Type;
use ratatui::{
    layout::{Constraint, Layout, Offset, Rect},
    style::Stylize,
    text::Line,
    Frame,
};

use crate::{
    color_consts,
    data::{MatrixTable, MatrixValues},
    error::AppError,
    h5f::{DatasetMeta, H5FNode},
};

use super::{
    dims::{render_dim_selector, HasMatrixSelection, MatrixSelection},
    state::AppState,
};

fn format_cell<T: Display>(v: &T) -> String {
    let s = format!("{v}");
    if s.len() > 10 {
        if let Ok(f) = s.parse::<f64>() {
            return format!("{:.4e}", f);
        }
    }
    s
}

pub fn render_not_yet_implemented(f: &mut Frame, area: &Rect, desc: &str) {
    let inner_area = area.inner(ratatui::layout::Margin {
        horizontal: 2,
        vertical: 1,
    });
    let unsupported_msg = "Not yet implemented:".to_string();
    f.render_widget(unsupported_msg, inner_area);
    let why = desc.to_string();
    f.render_widget(
        why,
        inner_area.inner(ratatui::layout::Margin {
            horizontal: 2,
            vertical: 1,
        }),
    );
}

pub fn render_matrix<T: H5Type + Display>(
    f: &mut Frame,
    area: &Rect,
    ds: &hdf5_metno::Dataset,
    attr: &DatasetMeta,
    node: &mut H5FNode,
    state: &mut AppState,
) -> Result<(), AppError> {
    let area_inner = area.inner(ratatui::layout::Margin {
        horizontal: 2,
        vertical: 1,
    });
    let shape_len = attr.shape.len();

    let matrix_area = if shape_len > 1 {
        let x_selectable_dims: Vec<usize> = attr
            .shape
            .iter()
            .enumerate()
            .filter(|(_, v)| **v > 1)
            .map(|(i, _)| i)
            .collect();

        let selected_indexe_length = node.selected_indexes.len();
        for i in 0..selected_indexe_length {
            if !x_selectable_dims.contains(&i) {
                node.selected_indexes[i] = 0;
            }
        }

        if !x_selectable_dims.contains(&node.selected_row) {
            node.selected_row = x_selectable_dims[0];
        }
        let areas_split =
            Layout::vertical(vec![Constraint::Length(4), Constraint::Min(1)]).split(area_inner);
        render_dim_selector(f, &areas_split[0], node, &attr.shape, true)?;
        areas_split[1].inner(ratatui::layout::Margin {
            horizontal: 0,
            vertical: 1,
        })
    } else {
        area_inner
    };
    let width = matrix_area.width;
    let height = matrix_area.height;

    let col_ds_len = attr
        .shape
        .get(node.selected_col)
        .map(|x| *x as u16)
        .unwrap_or(0);
    let row_ds_len = attr
        .shape
        .get(node.selected_row)
        .map(|x| *x as u16)
        .unwrap_or(0);

    let max_rows = height.min(row_ds_len);
    state.matrix_view_state.rows_currently_available = max_rows as usize;

    if shape_len == 1 {
        let est_cols = 1u16;
        state.matrix_view_state.cols_currently_available = est_cols as usize;
        let matrix_selection = MatrixSelection {
            cols: est_cols,
            rows: max_rows,
        };
        let slice_selection = state.get_matrix_selection(node, matrix_selection, &attr.shape);

        let mut rows_area_constraints = Vec::with_capacity(max_rows as usize);
        (0..max_rows).for_each(|_| {
            rows_area_constraints.push(Constraint::Length(1));
        });
        let rows_areas = Layout::vertical(rows_area_constraints).split(matrix_area);

        let data = ds.matrix_values::<T>(slice_selection)?;
        let mut i = state
            .matrix_view_state
            .row_offset
            .min(attr.shape[node.selected_row].saturating_sub(state.matrix_view_state.rows_currently_available));
        for (row_idx, d) in data.data.iter().enumerate() {
            let row_area = rows_areas[row_idx];
            let formatted = format_cell(d);
            let areas_split =
                Layout::horizontal(vec![Constraint::Max(15), Constraint::Min(16)]).split(row_area);
            let idx_area = areas_split[0];
            let value_area = areas_split[1];
            let val_bg_color = match (row_idx % 2) == 0 {
                true => match state.matrix_view_state.row_offset.is_multiple_of(2) {
                    true => color_consts::BG_VAL3_COLOR,
                    false => color_consts::BG_VAL4_COLOR,
                },
                false => match state.matrix_view_state.row_offset.is_multiple_of(2) {
                    true => color_consts::BG_VAL4_COLOR,
                    false => color_consts::BG_VAL3_COLOR,
                },
            };
            let idx_line = Line::from(format!("{i}")).left_aligned();
            let value_line = Line::from(formatted)
                .alignment(ratatui::layout::Alignment::Center)
                .bg(val_bg_color);
            f.render_widget(idx_line, idx_area);
            f.render_widget(value_line, value_area);
            i += 1;
        }
    } else {
        // Generous estimate: at least 6 chars per column
        let available_width = width.saturating_sub(15); // subtract row index column
        let est_cols = (available_width / 6).max(1).min(col_ds_len);
        state.matrix_view_state.cols_currently_available = est_cols as usize;
        let matrix_selection = MatrixSelection {
            cols: est_cols,
            rows: max_rows,
        };
        let slice_selection = state.get_matrix_selection(node, matrix_selection, &attr.shape);
        let data = ds.matrix_table::<T>(slice_selection)?;

        // Pre-format all cells and compute max width
        let est_rows = max_rows as usize;
        let est_cols_usize = est_cols as usize;
        let mut formatted: Vec<Vec<String>> = Vec::with_capacity(est_rows);
        let mut max_val_width: usize = 1;
        for i in 0..est_rows {
            let mut row_strings = Vec::with_capacity(est_cols_usize);
            for j in 0..est_cols_usize {
                let idx = if node.selected_row > node.selected_col {
                    (j, i)
                } else {
                    (i, j)
                };
                let s = match data.data.get(idx) {
                    Some(v) => format_cell(v),
                    None => String::new(),
                };
                if s.len() > max_val_width {
                    max_val_width = s.len();
                }
                row_strings.push(s);
            }
            formatted.push(row_strings);
        }

        let col_width = (max_val_width + 2) as u16;
        let actual_cols = (available_width / col_width).max(1).min(est_cols);

        // Update cols_currently_available with the actual number
        state.matrix_view_state.cols_currently_available = actual_cols as usize;

        let mut rows_area_constraints = Vec::with_capacity(max_rows as usize);
        (0..max_rows).for_each(|_| {
            rows_area_constraints.push(Constraint::Length(1));
        });
        let rows_areas = Layout::vertical(rows_area_constraints).split(matrix_area);

        // Column headers
        let mut col_constraint = Vec::with_capacity((actual_cols + 1) as usize);
        col_constraint.push(Constraint::Length(15));
        (0..actual_cols).for_each(|_| col_constraint.push(Constraint::Length(col_width)));
        let col_header_areas = Layout::horizontal(col_constraint).split(rows_areas[0]);

        for col in 0..actual_cols {
            let col_area = col_header_areas[(col + 1) as usize];
            let col_idx = state
                .matrix_view_state
                .col_offset
                .min(attr.shape[node.selected_col].saturating_sub(actual_cols as usize))
                + col as usize;
            f.render_widget(
                Line::from(format!("{col_idx}")).centered(),
                col_area.offset(Offset { x: 0, y: -1 }),
            );
        }

        // Data rows
        for i in 0..max_rows {
            let mut col_constraint = Vec::with_capacity((actual_cols + 1) as usize);
            col_constraint.push(Constraint::Length(15));
            (0..actual_cols).for_each(|_| col_constraint.push(Constraint::Length(col_width)));
            let row_area = rows_areas[i as usize];
            let col_areas = Layout::horizontal(col_constraint).split(row_area);
            let idx_area = col_areas[0];

            let idx = state.matrix_view_state.row_offset.min(
                attr.shape[node.selected_row].saturating_sub(state.matrix_view_state.rows_currently_available),
            ) + i as usize;
            let idx_line = Line::from(format!("{idx}")).left_aligned();
            f.render_widget(idx_line, idx_area);
            for j in 0..actual_cols {
                let val_area = col_areas[(j + 1) as usize];

                let val_bg_color = match (
                    (i as usize + state.matrix_view_state.row_offset).is_multiple_of(2),
                    (j as usize + state.matrix_view_state.col_offset).is_multiple_of(2),
                ) {
                    (true, true) => color_consts::BG_VAL3_COLOR,
                    (true, false) => color_consts::BG_VAL4_COLOR,
                    (false, true) => color_consts::BG_VAL1_COLOR,
                    (false, false) => color_consts::BG_VAL2_COLOR,
                };

                let cell_str = &formatted[i as usize][j as usize];
                if cell_str.is_empty() {
                    f.render_widget("None", val_area);
                } else {
                    f.render_widget(
                        Line::from(cell_str.as_str()).bg(val_bg_color).centered(),
                        val_area,
                    );
                }
            }
        }
    }

    Ok(())
}
