---
type: issue
state: open
created: 2026-03-02T09:34:07Z
updated: 2026-03-02T09:34:07Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/167
comments: 0
labels: feature, effort:medium, area:core, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:32.671Z
---

# [Issue 167]: [[Rust] Audit log data model and storage in fd5 crate](https://github.com/vig-os/fd5/issues/167)

Parent: #161

## Goal
Add `audit` module to the `fd5` Rust crate with `AuditEntry` struct and read/write functions.

## Spec
- `AuditEntry` struct (serde Serialize/Deserialize):
  - `parent_hash: String`
  - `timestamp: String` (ISO-8601)
  - `author: Author` (struct with `author_type: String`, `id: String`, `name: String`)
  - `message: String`
  - `changes: Vec<Change>` (struct with `action: String`, `path: String`, `attr: String`, `old: Option<String>`, `new: Option<String>`)
- `read_audit_log(file: &File) -> Fd5Result<Vec<AuditEntry>>` — read/parse `_fd5_audit_log`
- `append_audit_entry(file: &File, entry: &AuditEntry) -> Fd5Result<()>`
- JSON serialization via serde_json
- VarLenUnicode attribute storage

## TDD
- Test round-trip: write → read → assert equal
- Test append preserves existing entries
- Test empty/missing log returns Ok(vec![])
- Test malformed JSON returns clear error
- Test serde serialization matches Python format exactly
