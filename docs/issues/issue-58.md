---
type: issue
state: closed
created: 2026-02-25T05:57:42Z
updated: 2026-02-25T06:45:56Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/58
comments: 1
labels: area:imaging
assignees: gerchowl
milestone: Phase 3: Medical Imaging Schemas
projects: none
relationship: none
synced: 2026-02-26T04:15:57.562Z
---

# [Issue 58]: [[FEATURE] Implement device_data product schema (fd5-imaging)](https://github.com/vig-os/fd5/issues/58)

### Description

Implement the `device_data` product schema for device signals and acquisition logs (ECG, bellows, Prometheus metrics). Part of `fd5-imaging`.

See `white-paper.md` § `device_data` (line ~1349) for the full schema specification.

### Acceptance Criteria

- [ ] `DeviceDataSchema` class satisfying `ProductSchema` Protocol
- [ ] JSON Schema, root attrs, id_inputs, write() per white paper
- [ ] Entry point registered under `fd5.schemas`
- [ ] >= 90% test coverage with round-trip tests

### References

- `white-paper.md` § `device_data`
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 06:45 AM_

Merged — schema implemented with tests.

