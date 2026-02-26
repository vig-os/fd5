---
type: issue
state: closed
created: 2026-02-25T07:20:49Z
updated: 2026-02-25T07:52:04Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/89
comments: 1
labels: none
assignees: gerchowl
milestone: Phase 5: Ecosystem & Tooling
projects: none
relationship: none
synced: 2026-02-26T04:15:53.286Z
---

# [Issue 89]: [[CHORE] Add _types.py shared types module and SourceRecord dataclass](https://github.com/vig-os/fd5/issues/89)

### Description

DES-001 specifies `_types.py` for shared protocols, dataclasses, and type aliases. Currently `ProductSchema` protocol lives in `registry.py` and source records are plain dicts.

### Tasks

- [ ] Create `src/fd5/_types.py`
- [ ] Move `ProductSchema` protocol from `registry.py` to `_types.py` (re-export from registry for backward compat)
- [ ] Implement `SourceRecord` dataclass per DES-001 spec (path, content_hash, product_type, id)
- [ ] Update `write_sources()` in `provenance.py` to accept `SourceRecord` instances (keep dict support for backward compat)
- [ ] Add type aliases: `Fd5Path`, `ContentHash`, etc. as useful

### Acceptance Criteria

- [ ] `from fd5._types import ProductSchema, SourceRecord` works
- [ ] Existing code still works (backward compatible)
- [ ] >= 95% coverage

### References

- DES-001 § package structure: _types.py
- Audit: #81
- Epic: #85 | Refs: #10
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:52 AM_

Merged — implemented with tests.

