//! fd5 integrity verification.
//!
//! Recomputes the Merkle tree and compares with the stored `content_hash`.

use std::path::Path;

use hdf5_metno::File;

use crate::audit;
use crate::error::{Fd5Error, Fd5Result};
use crate::hash::compute_content_hash;

/// Verification status of an fd5 file.
#[derive(Debug, Clone)]
pub enum Fd5Status {
    /// Currently checking (used for UI state).
    Checking,
    /// Hash verified successfully.
    Valid(String),
    /// Hash mismatch.
    Invalid { stored: String, computed: String },
    /// Not an fd5 file (no content_hash attribute).
    NotFd5,
    /// Error during verification.
    Error(String),
}

/// Recompute the Merkle tree and compare with the stored `content_hash`.
///
/// Returns `true` if the hashes match, `false` otherwise (including
/// when `content_hash` is missing).
///
/// Direct equivalent of Python's `verify(path)`.
pub fn verify(path: &Path) -> Fd5Result<Fd5Status> {
    let file = File::open(path)?;
    verify_file(&file)
}

/// Verify an already-opened file.
pub fn verify_file(file: &File) -> Fd5Result<Fd5Status> {
    let group = file.as_group()?;

    // Read stored content_hash
    let stored = match group.attr("content_hash") {
        Ok(attr) => {
            let val: String = attr
                .read_scalar::<hdf5_metno::types::VarLenUnicode>()
                .map(|v| v.as_str().to_string())
                .or_else(|_| {
                    attr.read_scalar::<hdf5_metno::types::VarLenAscii>()
                        .map(|v| v.as_str().to_string())
                })
                .map_err(|e| Fd5Error::Other(format!("Failed to read content_hash: {e}")))?;
            val
        }
        Err(_) => return Ok(Fd5Status::NotFd5),
    };

    // Compute fresh hash
    let computed = compute_content_hash(file)?;

    if computed == stored {
        Ok(Fd5Status::Valid(stored))
    } else {
        Ok(Fd5Status::Invalid { stored, computed })
    }
}

/// Status of audit chain verification.
#[derive(Debug, Clone)]
pub enum ChainStatus {
    /// All entries form a valid chain. Contains the number of entries.
    Valid(usize),
    /// No audit log found on the file.
    NoLog,
    /// Chain is broken at the given index.
    BrokenChain {
        index: usize,
        expected: String,
        actual: String,
    },
    /// Error reading or parsing the audit log.
    Error(String),
}

/// Helper: write a VarLenUnicode attribute, deleting any existing one first.
fn write_vlu_attr(
    root: &hdf5_metno::Group,
    path: &str,
    attr_name: &str,
    vlu: &hdf5_metno::types::VarLenUnicode,
) -> Fd5Result<()> {
    if path == "/" {
        // Delete and recreate on root
        let _ = root.delete_attr(attr_name);
        root.new_attr::<hdf5_metno::types::VarLenUnicode>()
            .shape(())
            .create(attr_name)?
            .write_scalar(vlu)?;
    } else {
        let group = root.group(path)
            .map_err(|e| Fd5Error::Other(format!(
                "Cannot open group '{}': {e}", path
            )))?;
        let _ = group.delete_attr(attr_name);
        group
            .new_attr::<hdf5_metno::types::VarLenUnicode>()
            .shape(())
            .create(attr_name)?
            .write_scalar(vlu)?;
    }
    Ok(())
}

/// Verify the audit chain integrity.
///
/// Reconstructs each intermediate file state by reversing attribute edits
/// recorded in the audit entries, then checks that each entry's
/// `parent_hash` matches the Merkle hash of the reconstructed state.
///
/// This works by copying the file to a temporary location and
/// iteratively undoing changes to verify each link in the chain.
pub fn verify_chain(file: &File) -> Fd5Result<ChainStatus> {
    let entries = match audit::read_audit_log(file) {
        Ok(entries) if entries.is_empty() => return Ok(ChainStatus::NoLog),
        Ok(entries) => entries,
        Err(e) => return Ok(ChainStatus::Error(format!("{e}"))),
    };

    // We need a writable copy to reconstruct intermediate states.
    let src_path = file.filename();
    // Use a unique counter to avoid collisions between parallel calls.
    use std::sync::atomic::{AtomicU64, Ordering};
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let unique = COUNTER.fetch_add(1, Ordering::Relaxed);
    let tmp_path = std::env::temp_dir().join(format!(
        "fd5_chain_verify_{}_{}.fd5",
        std::process::id(),
        unique,
    ));
    std::fs::copy(&src_path, &tmp_path)?;

    let tmp_file = File::open_rw(&tmp_path)?;
    let root = tmp_file.as_group()?;

    // Verify from the last entry backwards to the first.
    // At each step, we undo the entry's changes and check the parent_hash.
    // We iterate in reverse: verify entry[n-1] first (current state minus
    // entry[n-1]'s changes), then entry[n-2], etc.
    for i in (0..entries.len()).rev() {
        let entry = &entries[i];

        // Undo this entry's attribute changes
        for change in &entry.changes {
            if let Some(ref old_val) = change.old {
                let attr_name = change.attr.as_str();
                let vlu: hdf5_metno::types::VarLenUnicode = old_val
                    .parse()
                    .map_err(|_| Fd5Error::Other("null byte in attr value".to_string()))?;

                write_vlu_attr(&root, &change.path, attr_name, &vlu)?;
            }
        }

        // Set audit log to entries[0..i] (before this entry was appended)
        let prefix = &entries[..i];
        if root.attr(audit::AUDIT_LOG_ATTR).is_ok() {
            root.delete_attr(audit::AUDIT_LOG_ATTR)?;
        }
        if !prefix.is_empty() {
            let json = serde_json::to_string(prefix)?;
            let vlu: hdf5_metno::types::VarLenUnicode = json
                .parse()
                .map_err(|_| Fd5Error::Other("null byte in JSON".to_string()))?;
            root.new_attr::<hdf5_metno::types::VarLenUnicode>()
                .shape(())
                .create(audit::AUDIT_LOG_ATTR)?
                .write_scalar(&vlu)?;
        }

        // Remove content_hash (it's excluded from Merkle but let's be clean)
        if root.attr("content_hash").is_ok() {
            root.delete_attr("content_hash")?;
        }

        tmp_file.flush()?;
        let computed = compute_content_hash(&tmp_file)?;

        if computed != entry.parent_hash {
            drop(tmp_file);
            let _ = std::fs::remove_file(&tmp_path);
            return Ok(ChainStatus::BrokenChain {
                index: i,
                expected: computed,
                actual: entry.parent_hash.clone(),
            });
        }
    }

    drop(tmp_file);
    let _ = std::fs::remove_file(&tmp_path);

    Ok(ChainStatus::Valid(entries.len()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audit::{AuditEntry, Author, Change};
    use crate::edit::{AttrValue, EditMode, EditPlan};
    use hdf5_metno::types::VarLenUnicode;
    use tempfile::TempDir;

    /// Helper: create a minimal fd5 file with content_hash and a string attr.
    fn make_test_file(dir: &TempDir) -> std::path::PathBuf {
        let path = dir.path().join("chain_test.fd5");
        let file = File::create(&path).expect("create file");
        let root = file.as_group().unwrap();

        let vlu: VarLenUnicode = "hello".parse().unwrap();
        root.new_attr::<VarLenUnicode>()
            .shape(())
            .create("calibration")
            .unwrap()
            .write_scalar(&vlu)
            .unwrap();

        let hash = crate::hash::compute_content_hash(&file).unwrap();
        let hash_vlu: VarLenUnicode = hash.parse().unwrap();
        root.new_attr::<VarLenUnicode>()
            .shape(())
            .create("content_hash")
            .unwrap()
            .write_scalar(&hash_vlu)
            .unwrap();

        file.flush().unwrap();
        drop(file);
        path
    }

    fn test_author() -> Author {
        Author {
            author_type: "orcid".to_string(),
            id: "0000-0001-2345-6789".to_string(),
            name: "Test User".to_string(),
        }
    }

    #[test]
    fn test_no_log_returns_nolog() {
        let dir = TempDir::new().unwrap();
        let path = make_test_file(&dir);
        let file = File::open(&path).unwrap();
        let status = verify_chain(&file).expect("verify_chain");
        match status {
            ChainStatus::NoLog => {} // expected
            other => panic!("expected NoLog, got {:?}", other),
        }
    }

    #[test]
    fn test_single_entry_valid() {
        let dir = TempDir::new().unwrap();
        let path = make_test_file(&dir);

        let plan = EditPlan {
            source_path: path.clone(),
            attr_path: "/".to_string(),
            attr_name: "calibration".to_string(),
            old_value: "hello".to_string(),
            new_value: AttrValue::String("world".to_string()),
            mode: EditMode::InPlace,
            message: Some("single edit".to_string()),
            author: test_author(),
        };
        plan.apply().expect("edit");

        let file = File::open(&path).unwrap();
        let status = verify_chain(&file).expect("verify_chain");
        match status {
            ChainStatus::Valid(n) => assert_eq!(n, 1),
            other => panic!("expected Valid(1), got {:?}", other),
        }
    }

    #[test]
    fn test_valid_chain() {
        let dir = TempDir::new().unwrap();
        let path = make_test_file(&dir);

        // Two sequential edits
        let plan1 = EditPlan {
            source_path: path.clone(),
            attr_path: "/".to_string(),
            attr_name: "calibration".to_string(),
            old_value: "hello".to_string(),
            new_value: AttrValue::String("world".to_string()),
            mode: EditMode::InPlace,
            message: Some("first".to_string()),
            author: test_author(),
        };
        plan1.apply().expect("edit1");

        let plan2 = EditPlan {
            source_path: path.clone(),
            attr_path: "/".to_string(),
            attr_name: "calibration".to_string(),
            old_value: "world".to_string(),
            new_value: AttrValue::String("final".to_string()),
            mode: EditMode::InPlace,
            message: Some("second".to_string()),
            author: test_author(),
        };
        plan2.apply().expect("edit2");

        let file = File::open(&path).unwrap();
        let status = verify_chain(&file).expect("verify_chain");
        match status {
            ChainStatus::Valid(n) => assert_eq!(n, 2),
            other => panic!("expected Valid(2), got {:?}", other),
        }
    }

    #[test]
    fn test_broken_chain_detected() {
        let dir = TempDir::new().unwrap();
        let path = make_test_file(&dir);

        // Make one real edit to create a valid audit entry
        let plan = EditPlan {
            source_path: path.clone(),
            attr_path: "/".to_string(),
            attr_name: "calibration".to_string(),
            old_value: "hello".to_string(),
            new_value: AttrValue::String("world".to_string()),
            mode: EditMode::InPlace,
            message: Some("legit edit".to_string()),
            author: test_author(),
        };
        plan.apply().expect("edit");

        // Now manually append a fake entry with a wrong parent_hash
        {
            let file = File::open_rw(&path).unwrap();
            let fake_entry = AuditEntry {
                parent_hash: "sha256:0000000000000000000000000000000000000000000000000000000000000000".to_string(),
                timestamp: "2026-03-02T15:00:00Z".to_string(),
                author: test_author(),
                message: "fake entry".to_string(),
                changes: vec![Change {
                    action: "edit".to_string(),
                    path: "/".to_string(),
                    attr: "calibration".to_string(),
                    old: Some("world".to_string()),
                    new: Some("tampered".to_string()),
                }],
            };
            crate::audit::append_audit_entry(&file, &fake_entry).expect("append");

            // Re-seal so Merkle verify passes but chain is broken
            let root = file.as_group().unwrap();
            if root.attr("content_hash").is_ok() {
                root.delete_attr("content_hash").unwrap();
            }
            let new_hash = crate::hash::compute_content_hash(&file).unwrap();
            let vlu: VarLenUnicode = new_hash.parse().unwrap();
            root.new_attr::<VarLenUnicode>()
                .shape(())
                .create("content_hash")
                .unwrap()
                .write_scalar(&vlu)
                .unwrap();
            file.flush().unwrap();
        }

        let file = File::open(&path).unwrap();
        let status = verify_chain(&file).expect("verify_chain");
        match status {
            ChainStatus::BrokenChain { index, .. } => assert_eq!(index, 1),
            other => panic!("expected BrokenChain at index 1, got {:?}", other),
        }
    }
}
