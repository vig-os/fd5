---
type: issue
state: open
created: 2026-03-02T09:34:15Z
updated: 2026-03-02T09:34:15Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/169
comments: 0
labels: feature, effort:medium, area:core, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:32.141Z
---

# [Issue 169]: [[Rust] Edit with audit logging in fd5 crate](https://github.com/vig-os/fd5/issues/169)

Parent: #161

## Goal
Extend `edit.rs` to append an audit entry on every attribute edit.

## Spec
- `EditPlan` gains: `message: Option<String>`, `author: Author`
- `EditResult` gains: `audit_entry: AuditEntry`
- `EditPlan::apply()` flow becomes:
  1. Read current content_hash → parent_hash
  2. Read current attribute value → old
  3. Write new attribute value
  4. Create AuditEntry
  5. Append to `_fd5_audit_log`
  6. Recompute content_hash
  7. Return EditResult with the entry

## TDD
- Test edit creates audit entry with correct parent_hash
- Test edit preserves existing log entries
- Test author from identity is recorded
- Test message defaults to "Edit <path>.<attr>"
- Test content_hash covers the audit log (tampering detected)
