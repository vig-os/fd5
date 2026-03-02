//! fd5 attribute editing with copy-on-write or in-place modes.
//!
//! After modifying an attribute, the `content_hash` is recomputed and
//! written back, re-sealing the file.

use std::path::{Path, PathBuf};

use hdf5_metno::types::VarLenUnicode;
use hdf5_metno::File;

use crate::audit::{self, AuditEntry, Author, Change};
use crate::error::Fd5Result;
use crate::hash::compute_content_hash;

/// Return the current UTC time as an ISO 8601 string.
///
/// Uses only `std::time` to avoid adding chrono as a dependency.
fn now_utc() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    // Convert epoch seconds to date/time components
    let days = secs / 86400;
    let time_of_day = secs % 86400;
    let hours = time_of_day / 3600;
    let minutes = (time_of_day % 3600) / 60;
    let seconds = time_of_day % 60;

    // Civil date from days since epoch (algorithm from Howard Hinnant)
    let z = days as i64 + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };

    format!("{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z", y, m, d, hours, minutes, seconds)
}

/// How the edit should be applied.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum EditMode {
    /// Copy the file first, edit the copy (safe default).
    CopyOnWrite,
    /// Edit the original file in place (dev/expert flag).
    InPlace,
}

/// Typed attribute values for writing.
#[derive(Debug, Clone)]
pub enum AttrValue {
    String(String),
    Int64(i64),
    Float64(f64),
}

/// Description of a planned edit — shown in confirmation dialog before applying.
#[derive(Debug, Clone)]
pub struct EditPlan {
    pub source_path: PathBuf,
    pub attr_path: String,
    pub attr_name: String,
    pub old_value: String,
    pub new_value: AttrValue,
    pub mode: EditMode,
    /// Optional human-readable message explaining the edit.
    pub message: Option<String>,
    /// Author identity for the audit trail.
    pub author: Author,
}

/// Result of a completed edit.
#[derive(Debug, Clone)]
pub struct EditResult {
    pub output_path: PathBuf,
    pub old_content_hash: String,
    pub new_content_hash: String,
}

fn make_vlu(s: &str) -> VarLenUnicode {
    s.parse().expect("content_hash should not contain null bytes")
}

impl EditPlan {
    /// Apply the edit plan: modify the attribute and re-seal with new content_hash.
    pub fn apply(&self) -> Fd5Result<EditResult> {
        let target_path = match self.mode {
            EditMode::CopyOnWrite => {
                let stem = self
                    .source_path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("file");
                let ext = self
                    .source_path
                    .extension()
                    .and_then(|s| s.to_str())
                    .unwrap_or("h5");
                let parent = self.source_path.parent().unwrap_or(Path::new("."));
                let target = parent.join(format!("{}_edited.{}", stem, ext));
                std::fs::copy(&self.source_path, &target)?;
                target
            }
            EditMode::InPlace => self.source_path.clone(),
        };

        // Open for read-write
        let file = File::open_rw(&target_path)?;
        let root_group: &hdf5_metno::Group = &*file;

        // Read old content_hash
        let old_hash = root_group
            .attr("content_hash")
            .ok()
            .and_then(|a| {
                a.read_scalar::<VarLenUnicode>()
                    .map(|v| v.as_str().to_string())
                    .ok()
            })
            .unwrap_or_default();

        // Write the new attribute value on the target object
        if self.attr_path == "/" {
            write_attr(root_group, &self.attr_name, &self.new_value)?;
        } else {
            let target_group = root_group.group(&self.attr_path)?;
            write_attr(&target_group, &self.attr_name, &self.new_value)?;
        }

        // Build the new-value string for the audit trail
        let new_value_str = match &self.new_value {
            AttrValue::String(s) => s.clone(),
            AttrValue::Int64(v) => v.to_string(),
            AttrValue::Float64(v) => v.to_string(),
        };

        // Create and append audit entry
        let entry = AuditEntry {
            parent_hash: old_hash.clone(),
            timestamp: now_utc(),
            author: self.author.clone(),
            message: self.message.clone().unwrap_or_default(),
            changes: vec![Change {
                action: "edit".to_string(),
                path: self.attr_path.clone(),
                attr: self.attr_name.clone(),
                old: Some(self.old_value.clone()),
                new: Some(new_value_str),
            }],
        };
        audit::append_audit_entry(&file, &entry)?;

        // Recompute and write new content_hash (now covers audit log too)
        let new_hash = compute_content_hash(&file)?;
        // Delete old content_hash and write new
        if root_group.attr("content_hash").is_ok() {
            root_group.delete_attr("content_hash")?;
        }
        let vlu = make_vlu(&new_hash);
        root_group
            .new_attr::<VarLenUnicode>()
            .shape(())
            .create("content_hash")?
            .write_scalar(&vlu)?;

        file.flush()?;

        Ok(EditResult {
            output_path: target_path,
            old_content_hash: old_hash,
            new_content_hash: new_hash,
        })
    }
}

/// Write a typed value as an HDF5 attribute, replacing any existing attribute.
fn write_attr(
    loc: &hdf5_metno::Location,
    name: &str,
    value: &AttrValue,
) -> Fd5Result<()> {
    // Delete existing attribute if present
    if loc.attr(name).is_ok() {
        loc.delete_attr(name)?;
    }

    match value {
        AttrValue::String(s) => {
            let vlu = make_vlu(s);
            loc.new_attr::<VarLenUnicode>()
                .shape(())
                .create(name)?
                .write_scalar(&vlu)?;
        }
        AttrValue::Int64(v) => {
            loc.new_attr::<i64>().shape(()).create(name)?.write_scalar(v)?;
        }
        AttrValue::Float64(v) => {
            loc.new_attr::<f64>().shape(()).create(name)?.write_scalar(v)?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audit::AUDIT_LOG_ATTR;
    use tempfile::TempDir;

    /// Helper: create a minimal fd5 file with a content_hash and a string attribute.
    fn make_editable_file(dir: &TempDir) -> PathBuf {
        let path = dir.path().join("test.fd5");
        let file = File::create(&path).expect("create HDF5 file");
        let root = file.as_group().unwrap();

        // Write a string attribute that we'll edit
        let vlu: VarLenUnicode = "1.0".parse().unwrap();
        root.new_attr::<VarLenUnicode>()
            .shape(())
            .create("calibration")
            .unwrap()
            .write_scalar(&vlu)
            .unwrap();

        // Compute and write content_hash
        let hash = compute_content_hash(&file).unwrap();
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
    fn test_edit_creates_audit_entry() {
        let dir = TempDir::new().unwrap();
        let path = make_editable_file(&dir);

        let plan = EditPlan {
            source_path: path.clone(),
            attr_path: "/".to_string(),
            attr_name: "calibration".to_string(),
            old_value: "1.0".to_string(),
            new_value: AttrValue::String("1.05".to_string()),
            mode: EditMode::InPlace,
            message: Some("Updated calibration factor".to_string()),
            author: test_author(),
        };

        let result = plan.apply().expect("edit should succeed");

        // Verify audit log was created
        let file = File::open(&result.output_path).unwrap();
        let log = audit::read_audit_log(&file).expect("read audit log");
        assert_eq!(log.len(), 1);
        assert_eq!(log[0].message, "Updated calibration factor");
        assert_eq!(log[0].changes.len(), 1);
        assert_eq!(log[0].changes[0].action, "edit");
        assert_eq!(log[0].changes[0].old, Some("1.0".to_string()));
        assert_eq!(log[0].changes[0].new, Some("1.05".to_string()));
    }

    #[test]
    fn test_edit_preserves_existing_log() {
        let dir = TempDir::new().unwrap();
        let path = make_editable_file(&dir);

        // First edit
        let plan1 = EditPlan {
            source_path: path.clone(),
            attr_path: "/".to_string(),
            attr_name: "calibration".to_string(),
            old_value: "1.0".to_string(),
            new_value: AttrValue::String("1.05".to_string()),
            mode: EditMode::InPlace,
            message: Some("First edit".to_string()),
            author: test_author(),
        };
        plan1.apply().expect("first edit");

        // Second edit
        let plan2 = EditPlan {
            source_path: path.clone(),
            attr_path: "/".to_string(),
            attr_name: "calibration".to_string(),
            old_value: "1.05".to_string(),
            new_value: AttrValue::String("1.1".to_string()),
            mode: EditMode::InPlace,
            message: Some("Second edit".to_string()),
            author: test_author(),
        };
        plan2.apply().expect("second edit");

        let file = File::open(&path).unwrap();
        let log = audit::read_audit_log(&file).expect("read");
        assert_eq!(log.len(), 2);
        assert_eq!(log[0].message, "First edit");
        assert_eq!(log[1].message, "Second edit");
    }

    #[test]
    fn test_audit_entry_has_correct_parent_hash() {
        let dir = TempDir::new().unwrap();
        let path = make_editable_file(&dir);

        // Read the original content_hash
        let original_hash = {
            let file = File::open(&path).unwrap();
            let root = file.as_group().unwrap();
            let attr = root.attr("content_hash").unwrap();
            attr.read_scalar::<VarLenUnicode>()
                .unwrap()
                .as_str()
                .to_string()
        };

        let plan = EditPlan {
            source_path: path.clone(),
            attr_path: "/".to_string(),
            attr_name: "calibration".to_string(),
            old_value: "1.0".to_string(),
            new_value: AttrValue::String("1.05".to_string()),
            mode: EditMode::InPlace,
            message: Some("test".to_string()),
            author: test_author(),
        };
        plan.apply().expect("edit");

        let file = File::open(&path).unwrap();
        let log = audit::read_audit_log(&file).expect("read");
        assert_eq!(log[0].parent_hash, original_hash);
    }

    #[test]
    fn test_content_hash_covers_audit_log() {
        let dir = TempDir::new().unwrap();
        let path = make_editable_file(&dir);

        let plan = EditPlan {
            source_path: path.clone(),
            attr_path: "/".to_string(),
            attr_name: "calibration".to_string(),
            old_value: "1.0".to_string(),
            new_value: AttrValue::String("1.05".to_string()),
            mode: EditMode::InPlace,
            message: Some("test".to_string()),
            author: test_author(),
        };
        let result = plan.apply().expect("edit");

        // Tamper with the audit log
        {
            let file = File::open_rw(&result.output_path).unwrap();
            let root = file.as_group().unwrap();
            if root.attr(AUDIT_LOG_ATTR).is_ok() {
                root.delete_attr(AUDIT_LOG_ATTR).unwrap();
            }
            let tampered: VarLenUnicode = "[]".parse().unwrap();
            root.new_attr::<VarLenUnicode>()
                .shape(())
                .create(AUDIT_LOG_ATTR)
                .unwrap()
                .write_scalar(&tampered)
                .unwrap();
            file.flush().unwrap();
        }

        // Verify should now fail
        let status = crate::verify::verify(&result.output_path).expect("verify call");
        match status {
            crate::verify::Fd5Status::Invalid { .. } => {} // expected
            other => panic!("expected Invalid after tampering, got {:?}", other),
        }
    }
}
