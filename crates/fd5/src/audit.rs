use serde::{Deserialize, Serialize};
use hdf5_metno::types::VarLenUnicode;
use hdf5_metno::File;
use crate::error::{Fd5Error, Fd5Result};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Author {
    #[serde(rename = "type")]
    pub author_type: String,
    pub id: String,
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Change {
    pub action: String,
    pub path: String,
    pub attr: String,
    pub old: Option<String>,
    pub new: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AuditEntry {
    pub parent_hash: String,
    pub timestamp: String,
    pub author: Author,
    pub message: String,
    pub changes: Vec<Change>,
}

pub fn read_audit_log(file: &File) -> Fd5Result<Vec<AuditEntry>> {
    let group = file.as_group()?;
    match group.attr("_fd5_audit_log") {
        Ok(attr) => {
            let raw = attr.read_scalar::<VarLenUnicode>()
                .map(|v| v.as_str().to_string())
                .map_err(|e| Fd5Error::Other(format!("Failed to read _fd5_audit_log: {e}")))?;
            let entries: Vec<AuditEntry> = serde_json::from_str(&raw)
                .map_err(|e| Fd5Error::Other(format!("Malformed audit log JSON: {e}")))?;
            Ok(entries)
        }
        Err(_) => Ok(vec![]),
    }
}

pub fn append_audit_entry(file: &File, entry: &AuditEntry) -> Fd5Result<()> {
    let group = file.as_group()?;
    let mut entries = read_audit_log(file)?;
    entries.push(entry.clone());
    let json = serde_json::to_string(&entries)
        .map_err(|e| Fd5Error::Other(format!("Failed to serialize audit log: {e}")))?;

    if group.attr("_fd5_audit_log").is_ok() {
        group.delete_attr("_fd5_audit_log")?;
    }
    let vlu: VarLenUnicode = json.parse().expect("audit JSON should not contain null bytes");
    group.new_attr::<VarLenUnicode>()
        .shape(())
        .create("_fd5_audit_log")?
        .write_scalar(&vlu)?;
    Ok(())
}

// Chain verification
#[derive(Debug, Clone)]
pub enum ChainStatus {
    Valid(usize),
    NoLog,
    BrokenChain { index: usize, expected: String, actual: String },
    Error(String),
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::NamedTempFile;

    fn make_test_file() -> (NamedTempFile, File) {
        let tmp = NamedTempFile::new().unwrap();
        let file = File::create(tmp.path()).unwrap();
        (tmp, file)
    }

    fn sample_author() -> Author {
        Author {
            author_type: "orcid".into(),
            id: "0000-0001-2345-6789".into(),
            name: "Test User".into(),
        }
    }

    fn sample_entry(parent_hash: &str, msg: &str) -> AuditEntry {
        AuditEntry {
            parent_hash: parent_hash.into(),
            timestamp: "2026-03-02T12:00:00Z".into(),
            author: sample_author(),
            message: msg.into(),
            changes: vec![Change {
                action: "set".into(),
                path: "/".into(),
                attr: "description".into(),
                old: Some("old value".into()),
                new: Some("new value".into()),
            }],
        }
    }

    #[test]
    fn read_audit_log_empty_file() {
        let (_tmp, file) = make_test_file();
        let entries = read_audit_log(&file).unwrap();
        assert!(entries.is_empty());
    }

    #[test]
    fn append_and_read_single_entry() {
        let (_tmp, file) = make_test_file();
        let entry = sample_entry("0000000000000000", "first edit");
        append_audit_entry(&file, &entry).unwrap();
        let entries = read_audit_log(&file).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].message, "first edit");
        assert_eq!(entries[0].author.name, "Test User");
    }

    #[test]
    fn append_multiple_entries() {
        let (_tmp, file) = make_test_file();
        let entry1 = sample_entry("0000000000000000", "edit one");
        let entry2 = sample_entry("abc123", "edit two");
        append_audit_entry(&file, &entry1).unwrap();
        append_audit_entry(&file, &entry2).unwrap();
        let entries = read_audit_log(&file).unwrap();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].message, "edit one");
        assert_eq!(entries[1].message, "edit two");
    }

    #[test]
    fn author_serialization_roundtrip() {
        let author = sample_author();
        let json = serde_json::to_string(&author).unwrap();
        let deserialized: Author = serde_json::from_str(&json).unwrap();
        assert_eq!(author, deserialized);
        // verify "type" field name in JSON
        assert!(json.contains("\"type\""));
    }

    #[test]
    fn change_with_none_old_value() {
        let change = Change {
            action: "set".into(),
            path: "/".into(),
            attr: "new_attr".into(),
            old: None,
            new: Some("value".into()),
        };
        let json = serde_json::to_string(&change).unwrap();
        let deserialized: Change = serde_json::from_str(&json).unwrap();
        assert_eq!(change, deserialized);
        assert!(deserialized.old.is_none());
    }
}
