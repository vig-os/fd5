---
type: issue
state: closed
created: 2026-02-25T07:20:43Z
updated: 2026-02-25T07:52:02Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/88
comments: 1
labels: none
assignees: gerchowl
milestone: Phase 5: Ecosystem & Tooling
projects: none
relationship: none
synced: 2026-02-26T04:15:53.592Z
---

# [Issue 88]: [[FEATURE] Add optional schema features: per-frame MIPs, gate data, embedded device_data](https://github.com/vig-os/fd5/issues/88)

### Description

Audit #81 identified several optional white-paper features not yet implemented in product schemas.

### Tasks

- [ ] **recon: per-frame MIPs** — Add `mips_per_frame/` group with per-frame coronal/sagittal MIPs for dynamic (4D+) data. See white-paper recon schema.
- [ ] **recon: gate data** — Add `gate_phase`, `gate_trigger/` sub-groups in `frames/` for gated reconstruction. See white-paper recon schema.
- [ ] **recon/listmode: embedded device_data** — Support optional `device_data/` group within recon and listmode files for ECG, bellows signals. See white-paper § device_data placement.
- [ ] **recon: provenance/dicom_header** — Support optional `dicom_header` JSON string and `per_slice_metadata` compound dataset under `provenance/`. See white-paper recon schema.
- [ ] Update JSON schemas for each product type to include optional fields
- [ ] Add tests for each optional feature (write + round-trip)

### Acceptance Criteria

- [ ] Optional features work when provided, files still valid when omitted
- [ ] JSON schemas updated with optional properties
- [ ] >= 90% coverage on new code
- [ ] No regression on existing tests

### References

- White-paper § recon, § listmode, § device_data placement
- Audit: #81
- Epic: #85 | Refs: #10
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:52 AM_

Merged — implemented with tests.

