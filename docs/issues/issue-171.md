---
type: issue
state: open
created: 2026-03-02T09:34:25Z
updated: 2026-03-02T09:34:25Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/171
comments: 0
labels: feature, effort:medium, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:31.629Z
---

# [Issue 171]: [[h5v] :log command, :edit audit trail, :identity command](https://github.com/vig-os/fd5/issues/171)

Parent: #161

## Goal
Wire up the audit trail in h5v: `:log` to view history, `:edit` to create audited edits, `:identity` to manage identity.

## Spec

### :log command
- Display audit history in the attribute/info panel or a dedicated view
- Show entries newest-first, git-log style
- Scrollable if many entries

### :edit with audit trail
- Existing `:edit`/`:edit!` commands now create audit entries
- Read identity from `~/.fd5/identity.toml`
- Show confirmation with old → new value and identity before applying

### :identity command
- `:identity` — show current identity
- `:identity set <type> <id> <name>` — save to `~/.fd5/identity.toml`

## TDD
- Test `:log` command parsing
- Test `:identity` command parsing
- Test edit creates audit entry via fd5 crate
