---
type: issue
state: open
created: 2026-03-02T09:33:40Z
updated: 2026-03-02T09:33:40Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/162
comments: 0
labels: feature, effort:medium, area:core, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:34.140Z
---

# [Issue 162]: [[Python] Audit log data model and storage (read/write _fd5_audit_log)](https://github.com/vig-os/fd5/issues/162)

Parent: #161

## Goal
Create `fd5.audit` module with `AuditEntry` dataclass and read/write functions for the `_fd5_audit_log` root attribute.

## Spec
- `AuditEntry` dataclass: `parent_hash`, `timestamp` (ISO-8601), `author` (dict with `type`/`id`/`name`), `message`, `changes` (list of dicts with `action`/`path`/`attr`/`old`/`new`)
- `read_audit_log(file: h5py.File) -> list[AuditEntry]` — parse JSON from `_fd5_audit_log` attribute
- `append_audit_entry(file: h5py.File, entry: AuditEntry)` — read existing log, append, write back as JSON
- `AuditEntry.to_dict()` / `AuditEntry.from_dict()` for JSON serialization
- The `_fd5_audit_log` attribute is a VarLenUnicode string (JSON array)
- NOT excluded from content_hash computation (tamper-evident)

## TDD
- Test round-trip: write entry → read back → assert equal
- Test append to existing log
- Test empty log returns []
- Test malformed JSON raises clear error
- Test entry validation (required fields)
