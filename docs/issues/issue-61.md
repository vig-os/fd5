---
type: issue
state: closed
created: 2026-02-25T05:58:14Z
updated: 2026-02-25T06:45:58Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/61
comments: 1
labels: epic, area:imaging
assignees: none
milestone: Phase 3: Medical Imaging Schemas
projects: none
relationship: none
synced: 2026-02-26T04:15:56.509Z
---

# [Issue 61]: [[EPIC] Phase 3: Medical Imaging Product Schemas](https://github.com/vig-os/fd5/issues/61)

### Description

Implement all remaining medical imaging product schemas for the `fd5-imaging` domain package.
Each schema follows the `ProductSchema` Protocol and is registered via entry points.

### Sub-issues

| # | Schema | White paper section |
|---|--------|-------------------|
| #51 | `listmode` — Event-based data | § listmode |
| #52 | `sinogram` — Projection data | § sinogram |
| #53 | `sim` — Simulation | § sim |
| #54 | `transform` — Spatial registrations | § transform |
| #55 | `calibration` — Detector/scanner calibration | § calibration |
| #56 | `spectrum` — Histogrammed/binned data | § spectrum |
| #57 | `roi` — Regions of interest | § roi |
| #58 | `device_data` — Device signals | § device_data |

### Dependency graph

All schemas are independent of each other. They depend only on:
- `fd5.registry` (ProductSchema Protocol) — completed (#17)
- `fd5_imaging.recon` (as reference implementation) — completed (#22)

All 8 schemas can be developed in parallel.

### References

- [RFC-001](docs/rfcs/RFC-001-2026-02-25-fd5-core-implementation.md) § Phase 3
- [DES-001](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md)
- `white-paper.md` § Product Schemas
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 06:45 AM_

All 8 Phase 3 schemas merged (#51-#58).

