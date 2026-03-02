use hdf5_metno::{Error, Hyperslab, Selection, SliceOrIndex};
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Margin, Offset, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Paragraph},
    Frame,
};

use crate::{color_consts, h5f::{H5FNode, Node}};

use super::state::AppState;

/// Convert a single voxel index to physical coordinate along a given axis using a 4x4 affine.
pub fn voxel_to_physical(affine: &[f64; 16], voxel: &[usize], dim: usize) -> f64 {
    if dim >= 3 {
        return f64::NAN; // Affine only covers spatial (first 3) dimensions
    }
    let mut phys = affine[dim * 4 + 3]; // translation component
    for j in 0..3 {
        let vox_j = if j < voxel.len() { voxel[j] as f64 } else { 0.0 };
        phys += affine[dim * 4 + j] * vox_j;
    }
    phys
}

pub enum DimSelectorMode {
    /// Chart mode: shows X axis selection
    Chart,
    /// Matrix mode: shows Row/Col labels
    Matrix,
    /// Image mode: shows H/W labels
    Image,
}

pub fn render_dim_selector(
    f: &mut Frame,
    area: &Rect,
    node: &mut H5FNode,
    shape: &[usize],
    row_columns: bool,
) -> Result<(), Error> {
    let mode = if row_columns {
        DimSelectorMode::Matrix
    } else {
        DimSelectorMode::Chart
    };
    render_dim_selector_with_mode(f, area, node, shape, mode)
}

pub fn render_dim_selector_with_mode(
    f: &mut Frame,
    area: &Rect,
    node: &mut H5FNode,
    shape: &[usize],
    mode: DimSelectorMode,
) -> Result<(), Error> {
    let x_selection = node.selected_x;
    let row_selection = node.selected_row;
    let col_selection = node.selected_col;
    let selected_dim = node.selected_dim;
    let index_selection = node.selected_indexes;
    let show_row_col = match mode {
        DimSelectorMode::Image | DimSelectorMode::Matrix => true,
        DimSelectorMode::Chart => false,
    };

    // Extract affine and reference frame from dataset metadata
    let (affine, ref_frame) = match &node.node {
        Node::Dataset(_, meta) => (meta.affine, meta.reference_frame.clone()),
        _ => (None, None),
    };

    let title = match &ref_frame {
        Some(rf) => format!("Slice selection [{}]", rf),
        None => "Slice selection".to_string(),
    };

    let block = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(color_consts::VARIABLE_BLUE_BUILTIN));
    f.render_widget(block, *area);

    let inner_area = area.inner(Margin {
        vertical: 1,
        horizontal: 1,
    });

    let (labels_area, dims_area) = {
        let chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Length(8), Constraint::Min(0)])
            .split(inner_area);
        (chunks[0], chunks[1])
    };
    // Print Shape: and View: on each line
    let shape_line = Line::from("Shape: ").alignment(Alignment::Right);
    let view_line = if !show_row_col {
        Line::from(" y = ").alignment(Alignment::Right)
    } else {
        Line::from(" view = ").alignment(Alignment::Right)
    };
    f.render_widget(shape_line, labels_area);
    f.render_widget(view_line, labels_area.offset(Offset { x: 0, y: 1 }));
    if affine.is_some() {
        let mm_line = Line::from(" mm = ").alignment(Alignment::Right);
        f.render_widget(mm_line, labels_area.offset(Offset { x: 0, y: 2 }));
    }

    let shape_strings = shape.iter().map(|s| s.to_string()).collect::<Vec<_>>();
    let bounds: Vec<u16> = shape_strings.iter().map(|s| s.len() as u16).collect();
    let (segments, spacers) = Layout::default()
        .direction(Direction::Horizontal)
        .spacing(3)
        .constraints(
            bounds
                .iter()
                .map(|&s| Constraint::Length(s.max(3)))
                .collect::<Vec<_>>(),
        )
        .split_with_spacers(dims_area);
    let spacers_len = spacers.len();

    for (i, spacer_area) in spacers.iter().enumerate() {
        if i == spacers_len - 1 {
            break;
        }
        let spacer = Paragraph::new(" | ")
            .block(Block::default().borders(Borders::NONE));
        f.render_widget(&spacer, spacer_area.offset(Offset { x: 0, y: 1 }));
        f.render_widget(spacer, *spacer_area);
    }

    let (row_label, col_label) = match mode {
        DimSelectorMode::Image => ("H", "W"),
        _ => ("Row", "Col"),
    };

    // Build voxel index array for physical coordinate computation
    let voxel_indexes: Vec<usize> = index_selection[..shape.len()].to_vec();

    for (i, dim) in shape_strings.iter().enumerate() {
        let dim_line = Line::from(dim.as_str()).alignment(Alignment::Left);
        f.render_widget(dim_line, segments[i]);
        if i == col_selection && show_row_col {
            let mut style = Style::default().bold().fg(color_consts::SELECTED_DIM);
            if i == selected_dim {
                style = style.underlined().underline_color(color_consts::SELECTED_INDEX);
            }
            let y_span = Span::from(col_label).style(style);
            let y_line = Line::from(y_span).alignment(Alignment::Center);
            f.render_widget(y_line, segments[i].offset(Offset { x: 0, y: 1 }));
        } else if i == row_selection && show_row_col {
            let mut style = Style::default().bold().fg(color_consts::SELECTED_DIM);
            if i == selected_dim {
                style = style.underlined().underline_color(color_consts::SELECTED_INDEX);
            }
            let x_span = Span::from(row_label).style(style);
            let x_line = Line::from(x_span).alignment(Alignment::Center);
            f.render_widget(x_line, segments[i].offset(Offset { x: 0, y: 1 }));
        } else if i == x_selection && !show_row_col {
            let x_span =
                Span::from("X").style(Style::default().bold().fg(color_consts::SELECTED_DIM));
            let x_line = Line::from(x_span).alignment(Alignment::Center);
            f.render_widget(x_line, segments[i].offset(Offset { x: 0, y: 1 }));
        } else if i == selected_dim {
            let selected_index = index_selection[i];
            let span = Span::from(format!("{}", selected_index)).style(
                Style::default()
                    .bold()
                    .underlined()
                    .underline_color(color_consts::SELECTED_INDEX),
            );
            let selected_line = Line::from(span).alignment(Alignment::Center);
            f.render_widget(selected_line, segments[i].offset(Offset { x: 0, y: 1 }));
        } else {
            let selected_index = index_selection[i];
            let selected_line =
                Line::from(format!("{}", selected_index)).alignment(Alignment::Center);
            f.render_widget(selected_line, segments[i].offset(Offset { x: 0, y: 1 }));
        }

        // Render physical coordinate on the third row if affine is available
        if let Some(ref aff) = affine {
            if i < 3 {
                let phys = voxel_to_physical(aff, &voxel_indexes, i);
                let phys_text = format!("{:.1}", phys);
                let phys_style = Style::default().fg(color_consts::VARIABLE_BLUE_BUILTIN);
                let phys_line =
                    Line::from(Span::styled(phys_text, phys_style)).alignment(Alignment::Center);
                f.render_widget(phys_line, segments[i].offset(Offset { x: 0, y: 2 }));
            }
        }
    }

    Ok(())
}

pub struct MatrixSelection {
    pub cols: u16,
    pub rows: u16,
}

pub trait HasMatrixSelection {
    fn get_matrix_selection(
        &self,
        node: &mut H5FNode,
        select: MatrixSelection,
        total_dims: &[usize],
    ) -> Selection;
}

impl HasMatrixSelection for AppState<'_> {
    fn get_matrix_selection(
        &self,
        node: &mut H5FNode,
        matrix_view: MatrixSelection,
        shape: &[usize],
    ) -> Selection {
        let mut slice: Vec<SliceOrIndex> = Vec::new();
        let total_dims = shape.len();
        if total_dims == 1 {
            slice.push(SliceOrIndex::SliceTo {
                start: self
                    .matrix_view_state
                    .row_offset
                    .min(shape[0] - self.matrix_view_state.rows_currently_available),
                step: 1,
                end: (self.matrix_view_state.row_offset + matrix_view.rows as usize).min(shape[0]),
                block: 1,
            });
        } else {
            let selections = node.selected_indexes;
            (0..total_dims).for_each(|dim| {
                if node.selected_col == dim {
                    slice.push(SliceOrIndex::SliceTo {
                        start: self
                            .matrix_view_state
                            .col_offset
                            .min(shape[dim] - self.matrix_view_state.cols_currently_available),
                        step: 1,
                        end: (self.matrix_view_state.col_offset + matrix_view.cols as usize)
                            .min(shape[dim]),
                        block: 1,
                    });
                } else if node.selected_row == dim {
                    slice.push(SliceOrIndex::SliceTo {
                        start: self
                            .matrix_view_state
                            .row_offset
                            .min(shape[dim] - self.matrix_view_state.rows_currently_available),
                        step: 1,
                        end: (self.matrix_view_state.row_offset + matrix_view.rows as usize)
                            .min(shape[dim]),
                        block: 1,
                    });
                } else {
                    slice.push(SliceOrIndex::Index(selections[dim]));
                }
            });
        }
        Selection::Hyperslab(Hyperslab::from(slice))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn voxel_to_physical_identity() {
        // Identity affine (row-major 4x4):
        // 1 0 0 0
        // 0 1 0 0
        // 0 0 1 0
        // 0 0 0 1
        let affine = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ];
        let voxel = [10, 20, 30];
        assert!((voxel_to_physical(&affine, &voxel, 0) - 10.0).abs() < 1e-10);
        assert!((voxel_to_physical(&affine, &voxel, 1) - 20.0).abs() < 1e-10);
        assert!((voxel_to_physical(&affine, &voxel, 2) - 30.0).abs() < 1e-10);
    }

    #[test]
    fn voxel_to_physical_scaled_translated() {
        // Scaled (2mm voxels) + translated (offset 100, 200, 300):
        // 2 0 0 100
        // 0 2 0 200
        // 0 0 2 300
        // 0 0 0   1
        let affine = [
            2.0, 0.0, 0.0, 100.0,
            0.0, 2.0, 0.0, 200.0,
            0.0, 0.0, 2.0, 300.0,
            0.0, 0.0, 0.0, 1.0,
        ];
        let voxel = [5, 10, 15];
        // dim 0: 2*5 + 100 = 110
        assert!((voxel_to_physical(&affine, &voxel, 0) - 110.0).abs() < 1e-10);
        // dim 1: 2*10 + 200 = 220
        assert!((voxel_to_physical(&affine, &voxel, 1) - 220.0).abs() < 1e-10);
        // dim 2: 2*15 + 300 = 330
        assert!((voxel_to_physical(&affine, &voxel, 2) - 330.0).abs() < 1e-10);
    }

    #[test]
    fn voxel_to_physical_dim_out_of_range() {
        let affine = [1.0; 16];
        let voxel = [1, 2, 3];
        assert!(voxel_to_physical(&affine, &voxel, 3).is_nan());
        assert!(voxel_to_physical(&affine, &voxel, 10).is_nan());
    }
}
