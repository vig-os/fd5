---
type: issue
state: closed
created: 2026-02-25T01:07:28Z
updated: 2026-02-25T02:22:29Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/13
comments: 1
labels: feature, effort:small, area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:56.280Z
---

# [Issue 13]: [[FEATURE] Implement physical units convention helpers](https://github.com/vig-os/fd5/issues/13)

### Description

Implement the `fd5.units` module: helpers for creating and reading physical quantities following the `value`/`units`/`unitSI` sub-group convention for attributes, and `units`/`unitSI` attrs for datasets.

### Acceptance Criteria

- [ ] `write_quantity(group, name, value, units, unit_si)` creates a sub-group with `value`, `units`, `unitSI` attrs
- [ ] `read_quantity(group, name)` returns `(value, units, unit_si)` tuple
- [ ] `set_dataset_units(dataset, units, unit_si)` sets `units` and `unitSI` attrs on a dataset
- [ ] Round-trip: write then read returns identical values
- [ ] ≥ 90% test coverage

### Dependencies

- No blockers; this is a leaf module

### References

- Epic: #11
- Design: [DES-001 § fd5.units](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5units--physical-quantity-convention)
- Whitepaper: [§ Units convention](white-paper.md#units-convention)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:22 AM_

Completed — merged into dev.

