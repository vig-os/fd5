---
type: issue
state: closed
created: 2026-02-25T05:54:07Z
updated: 2026-02-25T06:09:36Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/49
comments: 1
labels: area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-26T04:16:00.568Z
---

# [Issue 49]: [[TEST] End-to-end integration test for fd5 workflow](https://github.com/vig-os/fd5/issues/49)

### Description

All fd5 core modules have been implemented and unit-tested independently. We need an end-to-end integration test that exercises the full workflow:

1. `fd5.create()` context-manager to build an fd5 file with real data
2. Schema embedding and validation via `fd5.schema`
3. Content hashing via `fd5.hash`
4. Provenance writing via `fd5.provenance`
5. Filename generation via `fd5.naming`
6. CLI commands: `fd5 validate`, `fd5 info`, `fd5 schema-dump`
7. Manifest generation via `fd5 manifest`

### Acceptance Criteria

- [ ] Integration test in `tests/test_integration.py`
- [ ] Creates a real fd5 file using `fd5.create()` with the recon product schema
- [ ] Validates the file passes `fd5.schema.validate_file()`
- [ ] Verifies `fd5.hash` content_hash matches on re-read
- [ ] Tests CLI `validate` command against the created file
- [ ] Tests CLI `info` command shows correct metadata
- [ ] Tests CLI `manifest` command generates valid TOML
- [ ] All tests pass with existing modules (no new code needed beyond the test file)

### References

- RFC success criterion: "`fd5.create()` passes `fd5 validate`"
- All modules: fd5.create, fd5.hash, fd5.schema, fd5.provenance, fd5.naming, fd5.units, fd5.registry, fd5.h5io, fd5.manifest, fd5.cli
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 06:09 AM_

Completed — 20 integration tests covering full fd5 workflow merged into dev.

