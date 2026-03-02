//! User identity for audit trail authorship.
//!
//! Loads identity from `~/.fd5/identity.toml` and converts to [`Author`]
//! for audit entries.

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::audit::Author;
use crate::error::Fd5Result;

/// User identity for signing audit entries.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Identity {
    #[serde(rename = "type")]
    pub identity_type: String,
    pub id: String,
    pub name: String,
}

impl Identity {
    /// Create an anonymous identity (default when no config exists).
    pub fn anonymous() -> Self {
        todo!("Identity::anonymous not yet implemented")
    }

    /// Load identity from the default location (`~/.fd5/identity.toml`).
    pub fn load() -> Fd5Result<Self> {
        todo!("Identity::load not yet implemented")
    }

    /// Load identity from a specific TOML file.
    pub fn load_from(_path: &Path) -> Fd5Result<Self> {
        todo!("Identity::load_from not yet implemented")
    }

    /// Save identity to a specific TOML file.
    pub fn save_to(&self, _path: &Path) -> Fd5Result<()> {
        todo!("Identity::save_to not yet implemented")
    }

    /// Convert to an [`Author`] for use in audit entries.
    pub fn to_author(&self) -> Author {
        todo!("Identity::to_author not yet implemented")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_anonymous_default() {
        let id = Identity::anonymous();
        assert_eq!(id.identity_type, "anonymous");
        assert_eq!(id.id, "");
        assert_eq!(id.name, "Anonymous");
    }

    #[test]
    fn test_save_load_roundtrip() {
        let dir = TempDir::new().expect("tempdir");
        let path = dir.path().join("identity.toml");

        let id = Identity {
            identity_type: "orcid".to_string(),
            id: "0000-0001-2345-6789".to_string(),
            name: "Lars Gerchow".to_string(),
        };

        id.save_to(&path).expect("save");
        let loaded = Identity::load_from(&path).expect("load");
        assert_eq!(id, loaded);
    }

    #[test]
    fn test_missing_file_returns_anonymous() {
        let dir = TempDir::new().expect("tempdir");
        let path = dir.path().join("nonexistent.toml");

        let id = Identity::load_from(&path).expect("should not error");
        assert_eq!(id.identity_type, "anonymous");
    }

    #[test]
    fn test_to_author_conversion() {
        let id = Identity {
            identity_type: "orcid".to_string(),
            id: "0000-0001-2345-6789".to_string(),
            name: "Lars Gerchow".to_string(),
        };

        let author = id.to_author();
        assert_eq!(author.author_type, "orcid");
        assert_eq!(author.id, "0000-0001-2345-6789");
        assert_eq!(author.name, "Lars Gerchow");
    }
}
