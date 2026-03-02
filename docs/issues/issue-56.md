---
type: issue
state: closed
created: 2026-02-25T05:57:38Z
updated: 2026-02-25T06:45:53Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/56
comments: 1
labels: area:imaging
assignees: gerchowl
milestone: Phase 3: Medical Imaging Schemas
projects: none
relationship: none
synced: 2026-02-26T04:15:58.265Z
---

# [Issue 56]: [[FEATURE] Implement spectrum product schema (fd5-imaging)](https://github.com/vig-os/fd5/issues/56)

### Description

Implement the `spectrum` product schema for histogrammed/binned data (energy spectra, lifetime distributions). Part of `fd5-imaging`.

See `white-paper.md` § `spectrum` (line ~1089) for the full schema specification.

### Acceptance Criteria

- [ ] `SpectrumSchema` class satisfying `ProductSchema` Protocol
- [ ] JSON Schema, root attrs, id_inputs, write() per white paper
- [ ] Entry point registered under `fd5.schemas`
- [ ] >= 90% test coverage with round-trip tests

### References

- `white-paper.md` § `spectrum`
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 06:45 AM_

Merged — schema implemented with tests.

