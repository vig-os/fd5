use serde::{Deserialize, Serialize};

/// Application configuration, loaded from `~/.config/h5v/config.toml`.
///
/// All fields have sensible defaults. A missing or partial config file
/// is fine — only the values you specify override the defaults.
///
/// Example config.toml:
/// ```toml
/// [navigation]
/// hold_traverse_secs = 12.0   # slower hold scrolling
/// tap_window_ms = 180
///
/// [cache]
/// preload_mb = 256
/// ```
#[derive(Debug, Deserialize, Serialize)]
#[serde(default)]
pub struct Config {
    pub navigation: NavigationConfig,
    pub cache: CacheConfig,
    pub ui: UiConfig,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(default)]
pub struct NavigationConfig {
    /// Quick-tap detection window (ms). Two presses within this = double-tap.
    pub tap_window_ms: u64,
    /// Seconds to ramp from min to max hold velocity when holding an arrow key.
    pub hold_traverse_secs: f64,
    /// Double-tap jump as a fraction of dimension size (e.g. 0.05 = 5%).
    pub double_tap_fraction: f64,
    /// Minimum hold velocity floor (steps/sec) for small dimensions.
    pub min_hold_velocity: f64,
    /// Maximum hold velocity cap in absolute steps/sec.
    pub max_hold_velocity_steps: f64,
    /// Maximum hold velocity cap as fraction of dimension size per second.
    pub max_hold_velocity_pct: f64,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(default)]
pub struct CacheConfig {
    /// Total preload cache size in MB.
    pub preload_mb: usize,
    /// Max individual dataset size to cache (MB).
    pub max_dataset_mb: usize,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(default)]
pub struct UiConfig {
    /// Tree panel width as a percentage (0–100).
    pub tree_panel_pct: u16,
    /// Terminal width below which the tree panel is hidden.
    pub narrow_threshold: u16,
    /// Chart segment size threshold (points per segment).
    pub chart_segment_size: usize,
    /// Terminal event poll interval in ms (~frame rate target).
    pub poll_interval_ms: u64,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            navigation: NavigationConfig::default(),
            cache: CacheConfig::default(),
            ui: UiConfig::default(),
        }
    }
}

impl Default for NavigationConfig {
    fn default() -> Self {
        Self {
            tap_window_ms: 200,
            hold_traverse_secs: 12.0,
            double_tap_fraction: 0.05,
            min_hold_velocity: 3.0,
            max_hold_velocity_steps: 50.0,
            max_hold_velocity_pct: 0.05,
        }
    }
}

impl Default for CacheConfig {
    fn default() -> Self {
        Self {
            preload_mb: 512,
            max_dataset_mb: 256,
        }
    }
}

impl Default for UiConfig {
    fn default() -> Self {
        Self {
            tree_panel_pct: 30,
            narrow_threshold: 100,
            chart_segment_size: 250_000,
            poll_interval_ms: 16,
        }
    }
}

#[derive(Clone, Debug)]
pub enum ConfigValue {
    U16(u16),
    U64(u64),
    Usize(usize),
    F64(f64),
}

impl ConfigValue {
    pub fn to_display(&self) -> String {
        match self {
            ConfigValue::U16(v) => v.to_string(),
            ConfigValue::U64(v) => v.to_string(),
            ConfigValue::Usize(v) => v.to_string(),
            ConfigValue::F64(v) => format!("{v}"),
        }
    }

    pub fn parse(template: &ConfigValue, s: &str) -> Result<ConfigValue, String> {
        match template {
            ConfigValue::U16(_) => s
                .parse::<u16>()
                .map(ConfigValue::U16)
                .map_err(|e| e.to_string()),
            ConfigValue::U64(_) => s
                .parse::<u64>()
                .map(ConfigValue::U64)
                .map_err(|e| e.to_string()),
            ConfigValue::Usize(_) => s
                .parse::<usize>()
                .map(ConfigValue::Usize)
                .map_err(|e| e.to_string()),
            ConfigValue::F64(_) => s
                .parse::<f64>()
                .map(ConfigValue::F64)
                .map_err(|e| e.to_string()),
        }
    }

    fn as_f64(&self) -> f64 {
        match self {
            ConfigValue::U16(v) => *v as f64,
            ConfigValue::U64(v) => *v as f64,
            ConfigValue::Usize(v) => *v as f64,
            ConfigValue::F64(v) => *v,
        }
    }

    pub fn in_range(&self, min: &ConfigValue, max: &ConfigValue) -> bool {
        let v = self.as_f64();
        v >= min.as_f64() && v <= max.as_f64()
    }
}

pub struct FieldMeta {
    pub section: &'static str,
    pub key: &'static str,
    pub description: &'static str,
    pub default: ConfigValue,
    pub min: ConfigValue,
    pub max: ConfigValue,
}

impl Config {
    /// Load config from `~/.config/h5v/config.toml`, falling back to defaults.
    pub fn load() -> Self {
        let Some(config_dir) = dirs_config_path() else {
            return Self::default();
        };
        let config_path = config_dir.join("config.toml");
        let Ok(contents) = std::fs::read_to_string(&config_path) else {
            return Self::default();
        };
        match toml::from_str(&contents) {
            Ok(cfg) => cfg,
            Err(e) => {
                eprintln!("Warning: invalid config at {}: {e}", config_path.display());
                Self::default()
            }
        }
    }

    /// Returns all config fields with their metadata and current values.
    pub fn field_metas(&self) -> Vec<(FieldMeta, ConfigValue)> {
        vec![
            // Navigation
            (
                FieldMeta {
                    section: "Navigation",
                    key: "tap_window_ms",
                    description: "Quick-tap detection window (ms)",
                    default: ConfigValue::U64(200),
                    min: ConfigValue::U64(50),
                    max: ConfigValue::U64(1000),
                },
                ConfigValue::U64(self.navigation.tap_window_ms),
            ),
            (
                FieldMeta {
                    section: "Navigation",
                    key: "hold_traverse_secs",
                    description: "Secs to reach max hold speed",
                    default: ConfigValue::F64(12.0),
                    min: ConfigValue::F64(1.0),
                    max: ConfigValue::F64(120.0),
                },
                ConfigValue::F64(self.navigation.hold_traverse_secs),
            ),
            (
                FieldMeta {
                    section: "Navigation",
                    key: "double_tap_fraction",
                    description: "Double-tap jump fraction",
                    default: ConfigValue::F64(0.05),
                    min: ConfigValue::F64(0.01),
                    max: ConfigValue::F64(0.5),
                },
                ConfigValue::F64(self.navigation.double_tap_fraction),
            ),
            (
                FieldMeta {
                    section: "Navigation",
                    key: "min_hold_velocity",
                    description: "Min hold velocity (steps/sec)",
                    default: ConfigValue::F64(3.0),
                    min: ConfigValue::F64(1.0),
                    max: ConfigValue::F64(100.0),
                },
                ConfigValue::F64(self.navigation.min_hold_velocity),
            ),
            (
                FieldMeta {
                    section: "Navigation",
                    key: "max_hold_velocity_steps",
                    description: "Max hold velocity cap (steps/sec)",
                    default: ConfigValue::F64(50.0),
                    min: ConfigValue::F64(1.0),
                    max: ConfigValue::F64(1000.0),
                },
                ConfigValue::F64(self.navigation.max_hold_velocity_steps),
            ),
            (
                FieldMeta {
                    section: "Navigation",
                    key: "max_hold_velocity_pct",
                    description: "Max hold velocity cap (fraction/sec)",
                    default: ConfigValue::F64(0.05),
                    min: ConfigValue::F64(0.001),
                    max: ConfigValue::F64(1.0),
                },
                ConfigValue::F64(self.navigation.max_hold_velocity_pct),
            ),
            // Cache
            (
                FieldMeta {
                    section: "Cache",
                    key: "preload_mb",
                    description: "Preload cache size (MB)",
                    default: ConfigValue::Usize(512),
                    min: ConfigValue::Usize(0),
                    max: ConfigValue::Usize(16384),
                },
                ConfigValue::Usize(self.cache.preload_mb),
            ),
            (
                FieldMeta {
                    section: "Cache",
                    key: "max_dataset_mb",
                    description: "Max dataset to cache (MB)",
                    default: ConfigValue::Usize(256),
                    min: ConfigValue::Usize(0),
                    max: ConfigValue::Usize(8192),
                },
                ConfigValue::Usize(self.cache.max_dataset_mb),
            ),
            // UI
            (
                FieldMeta {
                    section: "UI",
                    key: "tree_panel_pct",
                    description: "Tree panel width (%)",
                    default: ConfigValue::U16(30),
                    min: ConfigValue::U16(10),
                    max: ConfigValue::U16(80),
                },
                ConfigValue::U16(self.ui.tree_panel_pct),
            ),
            (
                FieldMeta {
                    section: "UI",
                    key: "narrow_threshold",
                    description: "Narrow mode threshold (cols)",
                    default: ConfigValue::U16(100),
                    min: ConfigValue::U16(40),
                    max: ConfigValue::U16(500),
                },
                ConfigValue::U16(self.ui.narrow_threshold),
            ),
            (
                FieldMeta {
                    section: "UI",
                    key: "chart_segment_size",
                    description: "Chart segment points",
                    default: ConfigValue::Usize(250_000),
                    min: ConfigValue::Usize(1000),
                    max: ConfigValue::Usize(10_000_000),
                },
                ConfigValue::Usize(self.ui.chart_segment_size),
            ),
            (
                FieldMeta {
                    section: "UI",
                    key: "poll_interval_ms",
                    description: "Event poll interval (ms)",
                    default: ConfigValue::U64(16),
                    min: ConfigValue::U64(1),
                    max: ConfigValue::U64(200),
                },
                ConfigValue::U64(self.ui.poll_interval_ms),
            ),
        ]
    }

    /// Set a config field by key, validating range. Returns error message on failure.
    pub fn set_field(&mut self, key: &str, value: ConfigValue) -> Result<(), String> {
        match key {
            "tap_window_ms" => {
                if let ConfigValue::U64(v) = value {
                    self.navigation.tap_window_ms = v;
                    Ok(())
                } else {
                    Err("Expected integer".into())
                }
            }
            "hold_traverse_secs" => {
                if let ConfigValue::F64(v) = value {
                    self.navigation.hold_traverse_secs = v;
                    Ok(())
                } else {
                    Err("Expected float".into())
                }
            }
            "double_tap_fraction" => {
                if let ConfigValue::F64(v) = value {
                    self.navigation.double_tap_fraction = v;
                    Ok(())
                } else {
                    Err("Expected float".into())
                }
            }
            "min_hold_velocity" => {
                if let ConfigValue::F64(v) = value {
                    self.navigation.min_hold_velocity = v;
                    Ok(())
                } else {
                    Err("Expected float".into())
                }
            }
            "max_hold_velocity_steps" => {
                if let ConfigValue::F64(v) = value {
                    self.navigation.max_hold_velocity_steps = v;
                    Ok(())
                } else {
                    Err("Expected float".into())
                }
            }
            "max_hold_velocity_pct" => {
                if let ConfigValue::F64(v) = value {
                    self.navigation.max_hold_velocity_pct = v;
                    Ok(())
                } else {
                    Err("Expected float".into())
                }
            }
            "preload_mb" => {
                if let ConfigValue::Usize(v) = value {
                    self.cache.preload_mb = v;
                    Ok(())
                } else {
                    Err("Expected integer".into())
                }
            }
            "max_dataset_mb" => {
                if let ConfigValue::Usize(v) = value {
                    self.cache.max_dataset_mb = v;
                    Ok(())
                } else {
                    Err("Expected integer".into())
                }
            }
            "tree_panel_pct" => {
                if let ConfigValue::U16(v) = value {
                    self.ui.tree_panel_pct = v;
                    Ok(())
                } else {
                    Err("Expected integer".into())
                }
            }
            "narrow_threshold" => {
                if let ConfigValue::U16(v) = value {
                    self.ui.narrow_threshold = v;
                    Ok(())
                } else {
                    Err("Expected integer".into())
                }
            }
            "chart_segment_size" => {
                if let ConfigValue::Usize(v) = value {
                    self.ui.chart_segment_size = v;
                    Ok(())
                } else {
                    Err("Expected integer".into())
                }
            }
            "poll_interval_ms" => {
                if let ConfigValue::U64(v) = value {
                    self.ui.poll_interval_ms = v;
                    Ok(())
                } else {
                    Err("Expected integer".into())
                }
            }
            _ => Err(format!("Unknown config key: {key}")),
        }
    }

    /// Save current config to `~/.config/h5v/config.toml`.
    pub fn save(&self) -> Result<(), String> {
        let config_dir = dirs_config_path().ok_or("Could not determine config directory")?;
        std::fs::create_dir_all(&config_dir)
            .map_err(|e| format!("Could not create config dir: {e}"))?;
        let config_path = config_dir.join("config.toml");
        let toml_str =
            toml::to_string_pretty(self).map_err(|e| format!("Could not serialize config: {e}"))?;
        std::fs::write(&config_path, toml_str)
            .map_err(|e| format!("Could not write config: {e}"))?;
        Ok(())
    }
}

fn dirs_config_path() -> Option<std::path::PathBuf> {
    // XDG_CONFIG_HOME or ~/.config
    if let Ok(xdg) = std::env::var("XDG_CONFIG_HOME") {
        return Some(std::path::PathBuf::from(xdg).join("h5v"));
    }
    let home = std::env::var("HOME").ok()?;
    Some(std::path::PathBuf::from(home).join(".config").join("h5v"))
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── Default value tests ─────────────────────────────────────

    #[test]
    fn default_nav_values() {
        let cfg = Config::default();
        assert_eq!(cfg.navigation.tap_window_ms, 200);
        assert!((cfg.navigation.hold_traverse_secs - 12.0).abs() < f64::EPSILON);
    }

    #[test]
    fn default_cache_values() {
        let cfg = Config::default();
        assert_eq!(cfg.cache.preload_mb, 512);
        assert_eq!(cfg.cache.max_dataset_mb, 256);
    }

    #[test]
    fn default_ui_values() {
        let cfg = Config::default();
        assert_eq!(cfg.ui.tree_panel_pct, 30);
        assert_eq!(cfg.ui.poll_interval_ms, 16);
    }

    // ── ConfigValue::parse tests ─────────────────────────────────

    #[test]
    fn parse_u16() {
        let result = ConfigValue::parse(&ConfigValue::U16(0), "42").unwrap();
        assert!(matches!(result, ConfigValue::U16(42)));
    }

    #[test]
    fn parse_u64() {
        let result = ConfigValue::parse(&ConfigValue::U64(0), "999").unwrap();
        assert!(matches!(result, ConfigValue::U64(999)));
    }

    #[test]
    fn parse_f64() {
        let result = ConfigValue::parse(&ConfigValue::F64(0.0), "3.14").unwrap();
        match result {
            ConfigValue::F64(v) => assert!((v - 3.14).abs() < f64::EPSILON),
            _ => panic!("expected F64"),
        }
    }

    #[test]
    fn parse_invalid() {
        let result = ConfigValue::parse(&ConfigValue::U16(0), "abc");
        assert!(result.is_err());
    }

    // ── ConfigValue::in_range tests ──────────────────────────────

    #[test]
    fn in_range_true() {
        assert!(ConfigValue::U64(100).in_range(&ConfigValue::U64(50), &ConfigValue::U64(200)));
    }

    #[test]
    fn in_range_false() {
        assert!(!ConfigValue::U64(300).in_range(&ConfigValue::U64(50), &ConfigValue::U64(200)));
    }

    #[test]
    fn in_range_boundary() {
        assert!(ConfigValue::U64(50).in_range(&ConfigValue::U64(50), &ConfigValue::U64(200)));
        assert!(ConfigValue::U64(200).in_range(&ConfigValue::U64(50), &ConfigValue::U64(200)));
    }

    // ── Config::set_field tests ──────────────────────────────────

    #[test]
    fn set_field_valid() {
        let mut cfg = Config::default();
        cfg.set_field("tap_window_ms", ConfigValue::U64(150)).unwrap();
        assert_eq!(cfg.navigation.tap_window_ms, 150);
    }

    #[test]
    fn set_field_unknown() {
        let mut cfg = Config::default();
        let result = cfg.set_field("nope", ConfigValue::U64(1));
        assert!(result.is_err());
    }

    #[test]
    fn set_field_wrong_type() {
        let mut cfg = Config::default();
        let result = cfg.set_field("tap_window_ms", ConfigValue::F64(1.0));
        assert!(result.is_err());
    }

    // ── field_metas count ────────────────────────────────────────

    #[test]
    fn field_metas_count() {
        let cfg = Config::default();
        assert_eq!(cfg.field_metas().len(), 12);
    }
}
