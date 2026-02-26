---
type: issue
state: closed
created: 2026-02-25T05:57:13Z
updated: 2026-02-25T06:45:44Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/51
comments: 1
labels: area:imaging
assignees: gerchowl
milestone: Phase 3: Medical Imaging Schemas
projects: none
relationship: none
synced: 2026-02-26T04:16:00.238Z
---

# [Issue 51]: [[FEATURE] Implement listmode product schema (fd5-imaging)](https://github.com/vig-os/fd5/issues/51)

### Description

Implement the `listmode` product schema for event-based detector data (singles, coincidences, time markers). This is part of the `fd5-imaging` domain package.

See `white-paper.md` § `listmode` (line ~767) for the full schema specification.

### Key data structures

- `raw_data/` group with compound datasets for singles, coincidences, time markers
- `mode` attr (e.g., "list", "step-and-shoot")
- `table_pos`, `duration`, `z_min`, `z_max` root attrs
- `metadata/daq/` sub-group for DAQ parameters

### Acceptance Criteria

- [ ] `ListmodeSchema` class satisfying `ProductSchema` Protocol
- [ ] `json_schema()` returns valid JSON Schema matching white paper spec
- [ ] `required_root_attrs()` returns correct set
- [ ] `id_inputs()` returns identity fields
- [ ] `write()` creates HDF5 structure per white paper
- [ ] Entry point registered in `pyproject.toml` under `fd5.schemas`
- [ ] >= 90% test coverage
- [ ] Tests verify round-trip: create file → validate against schema

### Dependencies

- #17 (registry) — completed
- #22 (recon, as reference implementation) — completed

### References

- `white-paper.md` § `listmode` product schema
- `src/fd5/imaging/recon.py` as reference implementation
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 06:45 AM_

Merged — schema implemented with tests.

