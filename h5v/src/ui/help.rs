use ratatui::{
    layout::{Alignment, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};

const S: Style = Style::new();

fn section_style() -> Style {
    S.fg(Color::Yellow).add_modifier(Modifier::BOLD)
}
fn key_style() -> Style {
    S.fg(Color::Cyan).add_modifier(Modifier::BOLD)
}
fn desc_style() -> Style {
    S.fg(Color::Gray)
}
fn dim_style() -> Style {
    S.fg(Color::DarkGray)
}

fn push_section(lines: &mut Vec<Line<'static>>, title: &'static str) {
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        format!("  {title}"),
        section_style(),
    )));
    lines.push(Line::from(Span::styled(
        "  ────────────────────────────────────────",
        dim_style(),
    )));
}

fn push_row(lines: &mut Vec<Line<'static>>, key: &'static str, desc: &'static str) {
    lines.push(Line::from(vec![
        Span::raw("    "),
        Span::styled(format!("{:<16}", key), key_style()),
        Span::styled(desc, desc_style()),
    ]));
}

pub fn render_help(frame: &mut Frame, area: Rect) {
    let mut lines: Vec<Line> = Vec::new();

    // ── Global ──
    push_section(&mut lines, "Global");
    push_row(&mut lines, "q / ^c", "Quit");
    push_row(&mut lines, "?", "This help screen");
    push_row(&mut lines, "/", "Search (fuzzy path matching)");
    push_row(&mut lines, ":", "Command mode (:123 seek, :+/-N step, :settings)");
    push_row(&mut lines, "Tab", "Toggle Preview / Matrix view");
    push_row(&mut lines, "\u{21E7}\u{2190}\u{2192}", "Move focus: Tree \u{2194} Attributes/Content");
    push_row(&mut lines, "\u{21E7}\u{2191}\u{2193}", "Move focus: Attributes \u{2194} Content");
    push_row(&mut lines, "^b", "Toggle tree panel visibility");
    push_row(&mut lines, ".", "Repeat last command");
    push_row(&mut lines, "M", "Open multi-chart overlay");

    // ── Tree ──
    push_section(&mut lines, "Tree Panel");
    push_row(&mut lines, "\u{2191}\u{2193} / j/k", "Navigate up/down");
    push_row(&mut lines, "\u{2190}\u{2192} / h/l", "Collapse / Expand node");
    push_row(&mut lines, "Enter / Space", "Toggle expand (or load more)");
    push_row(&mut lines, "g / G", "Jump to top / bottom");
    push_row(&mut lines, "Home / End", "Jump to top / bottom");
    push_row(&mut lines, "^d / u", "Page down / up (10 items)");
    push_row(&mut lines, "m", "Add 1D dataset to multi-chart");
    push_row(&mut lines, "y", "Copy node path to clipboard");

    // ── Attributes ──
    push_section(&mut lines, "Attributes Panel");
    push_row(&mut lines, "\u{2191}\u{2193}", "Navigate attributes");
    push_row(&mut lines, "\u{2190}\u{2192}", "Select name / value column");
    push_row(&mut lines, "y", "Copy selected name or value");

    // ── Content (2D) ──
    push_section(&mut lines, "Content (2D datasets)");
    push_row(&mut lines, "PgUp / PgDn", "Scroll rows (matrix view)");
    push_row(&mut lines, "Home / End", "Jump to first / last row");

    // ── Content (3D+ slicing) ──
    push_section(&mut lines, "Content (3D+ datasets)");
    push_row(&mut lines, "\u{2191} tap", "Step \u{2212}1 along current dimension");
    push_row(&mut lines, "\u{2193} tap", "Step +1 along current dimension");
    push_row(&mut lines, "\u{2191}\u{2191} double", "Jump \u{2212}5% of dimension");
    push_row(&mut lines, "\u{2193}\u{2193} double", "Jump +5% of dimension");
    push_row(&mut lines, "\u{2191}\u{2191}\u{2191} triple", "Jump to start of dimension");
    push_row(&mut lines, "\u{2193}\u{2193}\u{2193} triple", "Jump to end of dimension");
    push_row(&mut lines, "Hold \u{2191}/\u{2193}", "Sweep (accelerating scroll)");
    push_row(&mut lines, "\u{2190}\u{2192}", "Cycle active dimension");
    push_row(&mut lines, "Enter", "Assign selected dim as stepping dim");

    // ── Command mode ──
    push_section(&mut lines, "Command Mode (press : to enter)");
    push_row(&mut lines, "123", "Seek to absolute index");
    push_row(&mut lines, "+N / -N", "Step by relative offset");
    push_row(&mut lines, "settings", "Open settings editor");
    push_row(&mut lines, "Enter", "Execute command");
    push_row(&mut lines, "Esc", "Cancel");

    // ── Search ──
    push_section(&mut lines, "Search Mode (press / to enter)");
    push_row(&mut lines, "type...", "Fuzzy filter HDF5 paths");
    push_row(&mut lines, "Enter", "Jump to selected match");
    push_row(&mut lines, "Esc", "Cancel and return");
    push_row(&mut lines, "q", "Quit application");

    // ── Settings ──
    push_section(&mut lines, "Settings (enter via :settings)");
    push_row(&mut lines, "\u{2191}\u{2193}", "Navigate fields");
    push_row(&mut lines, "Enter", "Edit selected field");
    push_row(&mut lines, "Esc", "Cancel edit / close settings");
    push_row(&mut lines, "S", "Save config to disk");
    push_row(&mut lines, "D", "Reset field to default");

    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "  Press Esc to close",
        dim_style(),
    )));

    let text = Text::from(lines);
    let paragraph = Paragraph::new(text)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::LightGreen))
                .border_type(ratatui::widgets::BorderType::Rounded)
                .title(" h5v Help ")
                .title_style(section_style())
                .title_alignment(Alignment::Center),
        )
        .wrap(Wrap { trim: false });
    frame.render_widget(paragraph, area);
}
