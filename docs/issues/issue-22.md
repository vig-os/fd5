---
type: issue
state: closed
created: 2026-02-25T01:09:22Z
updated: 2026-02-25T02:48:41Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/22
comments: 1
labels: feature, effort:large, area:imaging
assignees: gerchowl
milestone: Phase 2: Recon Schema + CLI
projects: none
relationship: none
synced: 2026-02-25T04:19:53.407Z
---

# [Issue 22]: [[FEATURE] Implement recon product schema (fd5-imaging)](https://github.com/vig-os/fd5/issues/22)

### Description

Implement the `recon` product schema as the first domain schema in `fd5-imaging`. This exercises all core structural patterns: N-dimensional volume datasets, multiscale pyramids, MIP projections, dynamic frames, affine transforms, and chunked compression.

The schema registers via `fd5.schemas` entry point so that `fd5.create(product="recon")` works.

### Acceptance Criteria

- [ ] `ReconSchema` class implements `ProductSchema` protocol
- [ ] Writes `volume` dataset (3D/4D/5D float32) with `affine`, `dimension_order`, `reference_frame`, `description` attrs
- [ ] Writes `pyramid/` group with configurable levels, `scale_factors`, `method` attrs
- [ ] Writes `mip_coronal` and `mip_sagittal` projection datasets
- [ ] Writes `frames/` group for 4D+ data: `frame_start`, `frame_duration`, `frame_label`, `frame_type`
- [ ] Chunking strategy matches whitepaper: `(1, Y, X)` for 3D, `(1, 1, Y, X)` for 4D
- [ ] Compression: gzip level 4
- [ ] `id_inputs` follows medical imaging convention: `timestamp + scanner + vendor_series_id`
- [ ] Registers via `fd5.schemas` entry point in `pyproject.toml`
- [ ] JSON Schema generation produces valid schema for `recon` product
- [ ] Integration test: create a full recon file → validate → verify content_hash
- [ ] ≥ 90% test coverage

### Dependencies

- Depends on #19 (`fd5.create` builder) — all core modules must be in place
- Depends on #17 (`registry`) for entry point registration

### References

- Epic: #11
- Design: [DES-001 § fd5_imaging.recon](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5_imagingrecon--recon-product-schema-domain-package)
- Whitepaper: [§ recon product schema](white-paper.md#recon----reconstruction)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:48 AM_

Completed — merged into dev.

