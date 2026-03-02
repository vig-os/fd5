use crate::error::AppError;

#[derive(Debug, Clone)]
pub enum Command {
    Increment(usize),
    Decrement(usize),
    Seek(usize),
    Settings,
    Verify,
    Edit {
        attr_name: String,
        value: String,
        in_place: bool,
    },
    Quit,
    Help,
    Noop,
}

pub struct CommandState {
    pub command_buffer: String,
    pub cursor: usize,
    pub last_command: Command,
}

impl CommandState {
    pub fn parse_command(&mut self) -> Result<Command, AppError> {
        let command = self.command_buffer.trim();
        match command {
            "settings" | "set" | "s" => {
                self.last_command = Command::Settings;
                return Ok(Command::Settings);
            }
            "q" => {
                self.last_command = Command::Quit;
                return Ok(Command::Quit);
            }
            "?" | "help" => {
                self.last_command = Command::Help;
                return Ok(Command::Help);
            }
            "verify" | "v" => {
                self.last_command = Command::Verify;
                return Ok(Command::Verify);
            }
            _ => {}
        }
        // :edit attr_name value  OR  :edit! attr_name value
        if let Some(rest) = command.strip_prefix("edit!").or_else(|| command.strip_prefix("edit")) {
            let in_place = command.starts_with("edit!");
            let rest = rest.trim();
            if rest.is_empty() {
                return Err(AppError::InvalidCommand(
                    "Usage: :edit <attr_name> <value> or :edit! <attr_name> <value>".to_string(),
                ));
            }
            let (attr_name, value) = match rest.split_once(' ') {
                Some((name, val)) => (name.trim().to_string(), val.trim().to_string()),
                None => {
                    return Err(AppError::InvalidCommand(
                        "Usage: :edit <attr_name> <value>".to_string(),
                    ));
                }
            };
            let cmd = Command::Edit {
                attr_name,
                value,
                in_place,
            };
            self.last_command = cmd.clone();
            return Ok(cmd);
        }
        let first_symbol_opt = command.chars().next();
        let Some(first_symbol) = first_symbol_opt else {
            return Ok(Command::Noop);
        };
        match first_symbol {
            '+' => {
                let increment: usize = command[1..].trim().parse().map_err(|_| {
                    AppError::InvalidCommand(format!("Invalid increment value: {}", command))
                })?;
                self.last_command = Command::Increment(increment);
                Ok(Command::Increment(increment))
            }
            '-' => {
                let decrement: usize = command[1..].trim().parse().map_err(|_| {
                    AppError::InvalidCommand(format!("Invalid decrement value: {}", command))
                })?;
                self.last_command = Command::Decrement(decrement);
                Ok(Command::Decrement(decrement))
            }
            _ => {
                let seek: usize = command.parse().map_err(|_| {
                    AppError::InvalidCommand(format!("Invalid seek value: {}", command))
                })?;
                self.last_command = Command::Seek(seek);
                Ok(Command::Seek(seek))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_cmd(input: &str) -> CommandState {
        CommandState {
            command_buffer: input.to_string(),
            cursor: 0,
            last_command: Command::Noop,
        }
    }

    #[test]
    fn parse_settings_full() {
        let mut cmd = make_cmd("settings");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Settings));
    }

    #[test]
    fn parse_settings_set() {
        let mut cmd = make_cmd("set");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Settings));
    }

    #[test]
    fn parse_settings_s() {
        let mut cmd = make_cmd("s");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Settings));
    }

    #[test]
    fn parse_quit() {
        let mut cmd = make_cmd("q");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Quit));
    }

    #[test]
    fn parse_help_question() {
        let mut cmd = make_cmd("?");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Help));
    }

    #[test]
    fn parse_help_word() {
        let mut cmd = make_cmd("help");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Help));
    }

    #[test]
    fn parse_empty() {
        let mut cmd = make_cmd("");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Noop));
    }

    #[test]
    fn parse_whitespace() {
        let mut cmd = make_cmd("   ");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Noop));
    }

    #[test]
    fn parse_increment() {
        let mut cmd = make_cmd("+5");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Increment(5)));
    }

    #[test]
    fn parse_increment_zero() {
        let mut cmd = make_cmd("+0");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Increment(0)));
    }

    #[test]
    fn parse_increment_large() {
        let mut cmd = make_cmd("+999");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Increment(999)));
    }

    #[test]
    fn parse_increment_space() {
        let mut cmd = make_cmd("+ 5");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Increment(5)));
    }

    #[test]
    fn parse_decrement() {
        let mut cmd = make_cmd("-3");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Decrement(3)));
    }

    #[test]
    fn parse_seek() {
        let mut cmd = make_cmd("42");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Seek(42)));
    }

    #[test]
    fn parse_seek_zero() {
        let mut cmd = make_cmd("0");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Seek(0)));
    }

    #[test]
    fn parse_invalid_increment() {
        let mut cmd = make_cmd("+abc");
        assert!(cmd.parse_command().is_err());
    }

    #[test]
    fn parse_invalid_garbage() {
        let mut cmd = make_cmd("garbage");
        assert!(cmd.parse_command().is_err());
    }

    #[test]
    fn parse_updates_last_command() {
        let mut cmd = make_cmd("+5");
        cmd.parse_command().unwrap();
        assert!(matches!(cmd.last_command, Command::Increment(5)));
    }

    // ── audit trail command tests (RED phase) ────────────────────

    #[test]
    fn parse_log() {
        let mut cmd = make_cmd("log");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Log));
    }

    #[test]
    fn parse_log_alias_l() {
        let mut cmd = make_cmd("l");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Log));
    }

    #[test]
    fn parse_identity() {
        let mut cmd = make_cmd("identity");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Identity));
    }

    #[test]
    fn parse_identity_alias_id() {
        let mut cmd = make_cmd("id");
        assert!(matches!(cmd.parse_command().unwrap(), Command::Identity));
    }

    #[test]
    fn parse_identity_set() {
        let mut cmd = make_cmd("identity set orcid 0000-0001 Lars");
        match cmd.parse_command().unwrap() {
            Command::IdentitySet { identity_type, id, name } => {
                assert_eq!(identity_type, "orcid");
                assert_eq!(id, "0000-0001");
                assert_eq!(name, "Lars");
            }
            other => panic!("Expected IdentitySet, got {:?}", other),
        }
    }

    #[test]
    fn parse_identity_set_multiword_name() {
        let mut cmd = make_cmd("identity set orcid 0000-0001 Lars Gerchow");
        match cmd.parse_command().unwrap() {
            Command::IdentitySet { identity_type, id, name } => {
                assert_eq!(identity_type, "orcid");
                assert_eq!(id, "0000-0001");
                assert_eq!(name, "Lars Gerchow");
            }
            other => panic!("Expected IdentitySet, got {:?}", other),
        }
    }

    #[test]
    fn parse_identity_set_missing_args() {
        let mut cmd = make_cmd("identity set orcid");
        assert!(cmd.parse_command().is_err());
    }

    #[test]
    fn parse_identity_set_no_args() {
        let mut cmd = make_cmd("identity set");
        assert!(cmd.parse_command().is_err());
    }
}
