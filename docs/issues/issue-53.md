---
type: issue
state: closed
created: 2026-02-25T05:57:33Z
updated: 2026-02-25T06:45:47Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/53
comments: 1
labels: area:imaging
assignees: gerchowl
milestone: Phase 3: Medical Imaging Schemas
projects: none
relationship: none
synced: 2026-02-26T04:15:59.597Z
---

# [Issue 53]: [[FEATURE] Implement sim product schema (fd5-imaging)](https://github.com/vig-os/fd5/issues/53)

### Description

Implement the `sim` product schema for simulation data (Monte Carlo, ground truth phantoms). Part of `fd5-imaging`.

See `white-paper.md` § `sim` (line ~858) for the full schema specification.

### Acceptance Criteria

- [ ] `SimSchema` class satisfying `ProductSchema` Protocol
- [ ] JSON Schema, root attrs, id_inputs, write() per white paper
- [ ] Entry point registered under `fd5.schemas`
- [ ] >= 90% test coverage with round-trip tests

### References

- `white-paper.md` § `sim`
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 06:45 AM_

Merged — schema implemented with tests.

