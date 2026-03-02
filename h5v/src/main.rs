use std::io::Write;

use clap::Parser;
use ratatui::crossterm::ExecutableCommand;

mod color_consts;
mod config;
mod data;
mod error;
mod h5f;
mod linking;
// mod scripting;
mod search;
mod sprint_attributes;
mod sprint_typedesc;
mod ui;
mod utils;

#[cfg(test)]
mod test_helpers;

use git_version::git_version;

use crate::error::AppError;
const GIT_VERSION: &str =
    git_version!(args = ["--always", "--dirty=-modified", "--tags", "--abbrev=4"]);

#[derive(Parser, Debug)]
#[clap(
    author = "Daniel F. Hauge animcuil@gmail.com",
    about = "HDF5 Terminal Viewer (h5v)",
    version = GIT_VERSION
)]
struct Args {
    /// Path to the HDF5 file to open
    files: Vec<String>,

    /// Open file in SWMR (Single Writer Multiple Reader) mode
    #[arg(long)]
    swmr: bool,
}

fn main() -> Result<(), AppError> {
    // Install panic hook to capture panics to a file (TUI hides stderr)
    std::panic::set_hook(Box::new(|info| {
        let _ = ratatui::crossterm::terminal::disable_raw_mode();
        let _ = std::io::stdout()
            .execute(ratatui::crossterm::terminal::LeaveAlternateScreen);
        let bt = std::backtrace::Backtrace::force_capture();
        let crash_msg = format!("PANIC: {}\nBacktrace:\n{:?}", info, bt);
        eprintln!("{}", crash_msg);
        // Also write to file in case stderr is lost with alternate screen
        if let Ok(mut f) = std::fs::File::create("/tmp/h5v_crash.log") {
            let _ = write!(f, "{}", crash_msg);
        }
    }));

    let args = Args::parse();
    let cfg = config::Config::load();

    match &args.files[..] {
        [] => Err(AppError::FileError(String::from(
            "No files given.\n Usage: h5v /path/to/file.h5",
        ))),
        [single] => ui::app::init(single.clone(), cfg, args.swmr),
        multiple => ui::app::init(linking::link(multiple)?, cfg, args.swmr),
    }
}
