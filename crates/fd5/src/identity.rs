use std::path::{Path, PathBuf};
use serde::{Deserialize, Serialize};
use crate::audit::Author;
use crate::error::{Fd5Error, Fd5Result};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IdentityConfig {
    pub identity: Identity,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Identity {
    #[serde(rename = "type")]
    pub identity_type: String,
    pub id: String,
    pub name: String,
}

impl Identity {
    pub fn anonymous() -> Self {
        Self { identity_type: "anonymous".into(), id: String::new(), name: "anonymous".into() }
    }

    pub fn to_author(&self) -> Author {
        Author { author_type: self.identity_type.clone(), id: self.id.clone(), name: self.name.clone() }
    }

    pub fn config_path() -> PathBuf {
        dirs::home_dir().unwrap_or_default().join(".fd5").join("identity.toml")
    }

    pub fn load() -> Fd5Result<Self> {
        Self::load_from(&Self::config_path())
    }

    pub fn load_from(path: &Path) -> Fd5Result<Self> {
        match std::fs::read_to_string(path) {
            Ok(content) => {
                let config: IdentityConfig = toml::from_str(&content)
                    .map_err(|e| Fd5Error::Other(format!("Invalid identity.toml: {e}")))?;
                Ok(config.identity)
            }
            Err(_) => Ok(Self::anonymous()),
        }
    }

    pub fn save_to(&self, path: &Path) -> Fd5Result<()> {
        let config = IdentityConfig { identity: self.clone() };
        let content = toml::to_string_pretty(&config)
            .map_err(|e| Fd5Error::Other(format!("Failed to serialize identity: {e}")))?;
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(path, content)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn anonymous_identity() {
        let id = Identity::anonymous();
        assert_eq!(id.identity_type, "anonymous");
        assert_eq!(id.name, "anonymous");
        assert!(id.id.is_empty());
    }

    #[test]
    fn to_author_conversion() {
        let id = Identity {
            identity_type: "orcid".into(),
            id: "0000-0001".into(),
            name: "Lars".into(),
        };
        let author = id.to_author();
        assert_eq!(author.author_type, "orcid");
        assert_eq!(author.id, "0000-0001");
        assert_eq!(author.name, "Lars");
    }

    #[test]
    fn load_missing_file_returns_anonymous() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("nonexistent.toml");
        let id = Identity::load_from(&path).unwrap();
        assert_eq!(id.identity_type, "anonymous");
    }

    #[test]
    fn save_and_load_roundtrip() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("identity.toml");
        let id = Identity {
            identity_type: "orcid".into(),
            id: "0000-0001-2345-6789".into(),
            name: "Test Researcher".into(),
        };
        id.save_to(&path).unwrap();
        let loaded = Identity::load_from(&path).unwrap();
        assert_eq!(loaded.identity_type, "orcid");
        assert_eq!(loaded.id, "0000-0001-2345-6789");
        assert_eq!(loaded.name, "Test Researcher");
    }

    #[test]
    fn config_path_ends_with_identity_toml() {
        let p = Identity::config_path();
        assert!(p.ends_with("identity.toml"));
        assert!(p.to_str().unwrap().contains(".fd5"));
    }

    #[test]
    fn load_invalid_toml_returns_error() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("bad.toml");
        std::fs::write(&path, "this is not valid toml {{{{").unwrap();
        let result = Identity::load_from(&path);
        assert!(result.is_err());
    }
}
