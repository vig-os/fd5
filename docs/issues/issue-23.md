---
type: issue
state: closed
created: 2026-02-25T01:09:33Z
updated: 2026-02-25T02:48:42Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/23
comments: 1
labels: feature, effort:medium, area:core
assignees: gerchowl
milestone: Phase 2: Recon Schema + CLI
projects: none
relationship: none
synced: 2026-02-25T04:19:53.120Z
---

# [Issue 23]: [[FEATURE] Implement CLI commands (validate, info, schema-dump, manifest)](https://github.com/vig-os/fd5/issues/23)

### Description

Implement the `fd5.cli` module: a `click` command group providing `fd5 validate`, `fd5 info`, `fd5 schema-dump`, and `fd5 manifest` subcommands.

### Acceptance Criteria

- [ ] `fd5 validate <file>` validates against embedded schema and verifies `content_hash`; exits 0 on success, 1 on failure with structured error output
- [ ] `fd5 info <file>` prints root attrs and structure summary (product type, id, timestamp, content_hash, dataset shapes)
- [ ] `fd5 schema-dump <file>` extracts and pretty-prints the `_schema` JSON attribute
- [ ] `fd5 manifest <dir>` generates `manifest.toml` from fd5 files in the directory
- [ ] Console script entry point `fd5` configured in `pyproject.toml`
- [ ] `fd5 --help` shows available subcommands
- [ ] ≥ 90% test coverage

### Dependencies

- Depends on #15 (`schema`) for validate and schema-dump
- Depends on #14 (`hash`) for validate (content_hash verification)
- Depends on #20 (`manifest`) for manifest command
- Depends on #12 (`h5io`) for info command

### References

- Epic: #11
- Design: [DES-001 § fd5.cli](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5cli--command-line-interface)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:48 AM_

Completed — merged into dev.

