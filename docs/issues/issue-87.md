---
type: issue
state: closed
created: 2026-02-25T07:20:34Z
updated: 2026-02-25T07:52:00Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/87
comments: 1
labels: none
assignees: gerchowl
milestone: Phase 5: Ecosystem & Tooling
projects: none
relationship: none
synced: 2026-02-26T04:15:53.952Z
---

# [Issue 87]: [[FEATURE] Implement schema migration tool (fd5.migrate)](https://github.com/vig-os/fd5/issues/87)

### Description

Implement `fd5.migrate` module for upgrading fd5 files when product schemas evolve. The white-paper specifies additive-only schema evolution with `_schema_version` bumps, but no migration tooling exists yet.

### Tasks

- [ ] Create `src/fd5/migrate.py` with `migrate(path, target_version) -> Path` function
- [ ] Read `_schema_version` and `product` from source file
- [ ] Look up migration functions registered per product type and version pair
- [ ] Create new fd5 file with upgraded schema, preserving data and provenance
- [ ] Add `fd5 migrate <file> [--target-version N]` CLI command
- [ ] Migration registry: allow product schemas to register upgrade functions
- [ ] Add tests with a mock schema version upgrade scenario

### Acceptance Criteria

- [ ] Migration produces valid fd5 file that passes `fd5 validate`
- [ ] Original file is not modified (immutability preserved)
- [ ] Provenance chain links migrated file to original
- [ ] >= 90% coverage

### References

- White-paper § Versioning / Migration and upgrades (line ~1744)
- RFC-001 § Phase 5
- Epic: #85 | Refs: #10
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:51 AM_

Merged — implemented with tests.

