---
type: issue
state: open
created: 2026-03-02T09:33:51Z
updated: 2026-03-02T09:33:51Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/164
comments: 0
labels: feature, effort:medium, area:core, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:33.474Z
---

# [Issue 164]: [[Python] fd5 edit CLI command with audit logging](https://github.com/vig-os/fd5/issues/164)

Parent: #161

## Goal
Add `fd5 edit` CLI subcommand that modifies an attribute and appends an audit log entry.

## Spec
- `fd5 edit <file> <path>.<attr> <value> [--message MSG] [--in-place]`
- Default: copy-on-write (creates `_edited.h5` copy)
- `--in-place`: edit original file
- `--message/-m`: commit message (optional, defaults to "Edit <path>.<attr>")
- Reads identity from `~/.fd5/identity.toml`
- Creates `AuditEntry` with: parent_hash, timestamp, author, message, changes
- Appends entry to `_fd5_audit_log`, then recomputes content_hash

## Flow
1. Open file (copy or in-place)
2. Read current content_hash → parent_hash
3. Read current attribute value → old
4. Write new attribute value
5. Append AuditEntry to `_fd5_audit_log`
6. Recompute and write content_hash

## TDD
- Test edit creates audit entry
- Test edit preserves existing audit log entries
- Test copy-on-write creates new file
- Test in-place modifies original
- Test message defaults
- Test identity is recorded
