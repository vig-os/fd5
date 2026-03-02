---
type: issue
state: closed
created: 2026-02-25T05:57:31Z
updated: 2026-02-25T06:45:46Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/52
comments: 1
labels: area:imaging
assignees: gerchowl
milestone: Phase 3: Medical Imaging Schemas
projects: none
relationship: none
synced: 2026-02-26T04:15:59.921Z
---

# [Issue 52]: [[FEATURE] Implement sinogram product schema (fd5-imaging)](https://github.com/vig-os/fd5/issues/52)

### Description

Implement the `sinogram` product schema for projection data (Radon transforms, k-space). Part of `fd5-imaging`.

See `white-paper.md` § `sinogram` (line ~814) for the full schema specification.

### Acceptance Criteria

- [ ] `SinogramSchema` class satisfying `ProductSchema` Protocol
- [ ] JSON Schema, root attrs, id_inputs, write() per white paper
- [ ] Entry point registered under `fd5.schemas`
- [ ] >= 90% test coverage with round-trip tests

### References

- `white-paper.md` § `sinogram`
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 06:45 AM_

Merged — schema implemented with tests.

