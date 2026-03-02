//! Audit trail for fd5 files.
//!
//! Stores a tamper-evident chain of `AuditEntry` records in the
//! `_fd5_audit_log` root attribute (JSON array).  Because this attribute
//! is NOT in `EXCLUDED_ATTRS`, it participates in the Merkle tree and
//! any modification is detected by `verify`.

use serde::{Deserialize, Serialize};

use hdf5_metno::types::VarLenUnicode;
use hdf5_metno::File;

use crate::error::{Fd5Error, Fd5Result};

/// The HDF5 attribute name where the audit log lives.
pub const AUDIT_LOG_ATTR: &str = "_fd5_audit_log";

/// Identity of the person or system that performed a change.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Author {
    #[serde(rename = "type")]
    pub author_type: String,
    pub id: String,
    pub name: String,
}

/// A single change within an audit entry.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Change {
    pub action: String,
    pub path: String,
    pub attr: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub old: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub new: Option<String>,
}

/// One entry in the audit chain.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AuditEntry {
    pub parent_hash: String,
    pub timestamp: String,
    pub author: Author,
    pub message: String,
    pub changes: Vec<Change>,
}

/// Read the audit log from an fd5 file.
///
/// Returns an empty `Vec` if the `_fd5_audit_log` attribute does not exist.
pub fn read_audit_log(file: &File) -> Fd5Result<Vec<AuditEntry>> {
    let root = file.as_group()?;
    let attr = match root.attr(AUDIT_LOG_ATTR) {
        Ok(a) => a,
        Err(_) => return Ok(Vec::new()),
    };

    let raw: String = attr
        .read_scalar::<VarLenUnicode>()
        .map(|v| v.as_str().to_string())
        .map_err(|e| Fd5Error::Other(format!("Failed to read {AUDIT_LOG_ATTR}: {e}")))?;

    let entries: Vec<AuditEntry> = serde_json::from_str(&raw)?;
    Ok(entries)
}

/// Append an audit entry to the log, preserving existing entries.
pub fn append_audit_entry(file: &File, entry: &AuditEntry) -> Fd5Result<()> {
    let root = file.as_group()?;

    // Read existing entries (or start with empty vec)
    let mut entries = read_audit_log(file)?;
    entries.push(entry.clone());

    let json = serde_json::to_string(&entries)?;
    let vlu: VarLenUnicode = json
        .parse()
        .map_err(|_| Fd5Error::Other("audit JSON contains null bytes".to_string()))?;

    // Delete old attribute if present, then write new
    if root.attr(AUDIT_LOG_ATTR).is_ok() {
        root.delete_attr(AUDIT_LOG_ATTR)?;
    }
    root.new_attr::<VarLenUnicode>()
        .shape(())
        .create(AUDIT_LOG_ATTR)?
        .write_scalar(&vlu)?;

    file.flush()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::NamedTempFile;

    /// Helper: create a minimal HDF5 file with a content_hash attribute.
    fn make_test_file() -> (NamedTempFile, File) {
        let tmp = NamedTempFile::new().expect("create temp file");
        let path = tmp.path();
        let file = File::create(path).expect("create HDF5 file");
        let root = file.as_group().unwrap();

        // Write a content_hash attribute so it behaves like an fd5 file
        let vlu: VarLenUnicode = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
            .parse()
            .unwrap();
        root.new_attr::<VarLenUnicode>()
            .shape(())
            .create("content_hash")
            .unwrap()
            .write_scalar(&vlu)
            .unwrap();

        file.flush().unwrap();
        (tmp, file)
    }

    fn sample_author() -> Author {
        Author {
            author_type: "orcid".to_string(),
            id: "0000-0001-2345-6789".to_string(),
            name: "Test User".to_string(),
        }
    }

    fn sample_entry(parent_hash: &str) -> AuditEntry {
        AuditEntry {
            parent_hash: parent_hash.to_string(),
            timestamp: "2026-03-02T14:30:00Z".to_string(),
            author: sample_author(),
            message: "Updated calibration factor".to_string(),
            changes: vec![Change {
                action: "edit".to_string(),
                path: "/group".to_string(),
                attr: "calibration".to_string(),
                old: Some("1.0".to_string()),
                new: Some("1.05".to_string()),
            }],
        }
    }

    #[test]
    fn test_audit_entry_serde() {
        let entry = sample_entry("sha256:abc123");
        let json = serde_json::to_string(&entry).expect("serialize");
        let roundtrip: AuditEntry = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(entry, roundtrip);

        // Verify JSON field names match Python format
        let val: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert!(val.get("parent_hash").is_some());
        assert!(val.get("timestamp").is_some());
        assert!(val.get("author").is_some());
        assert!(val.get("message").is_some());
        assert!(val.get("changes").is_some());

        // Author must use "type" not "author_type" in JSON
        let author_val = val.get("author").unwrap();
        assert!(author_val.get("type").is_some());
        assert!(author_val.get("author_type").is_none());
    }

    #[test]
    fn test_read_empty_log() {
        let (_tmp, file) = make_test_file();
        let log = read_audit_log(&file).expect("read_audit_log should succeed");
        assert!(log.is_empty(), "empty file should have no audit entries");
    }

    #[test]
    fn test_write_read_roundtrip() {
        let (_tmp, file) = make_test_file();
        let entry = sample_entry("sha256:abc123");

        append_audit_entry(&file, &entry).expect("append should succeed");
        let log = read_audit_log(&file).expect("read should succeed");

        assert_eq!(log.len(), 1);
        assert_eq!(log[0], entry);
    }

    #[test]
    fn test_append_preserves_existing() {
        let (_tmp, file) = make_test_file();
        let entry1 = sample_entry("sha256:first");
        let entry2 = sample_entry("sha256:second");

        append_audit_entry(&file, &entry1).expect("first append");
        append_audit_entry(&file, &entry2).expect("second append");

        let log = read_audit_log(&file).expect("read");
        assert_eq!(log.len(), 2);
        assert_eq!(log[0], entry1);
        assert_eq!(log[1], entry2);
    }

    #[test]
    fn test_malformed_json_error() {
        let (_tmp, file) = make_test_file();
        let root = file.as_group().unwrap();

        // Write malformed JSON directly
        let bad_json: VarLenUnicode = "not valid json [[[".parse().unwrap();
        root.new_attr::<VarLenUnicode>()
            .shape(())
            .create(AUDIT_LOG_ATTR)
            .unwrap()
            .write_scalar(&bad_json)
            .unwrap();

        let result = read_audit_log(&file);
        assert!(result.is_err(), "malformed JSON should produce an error");
    }
}
