---
type: issue
state: open
created: 2026-02-25T22:30:21Z
updated: 2026-02-25T22:30:21Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/141
comments: 0
labels: docs, area:docs, effort:medium
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:45.955Z
---

# [Issue 141]: [[DOCS] Add positioning document: fd5 vs Zarr, NeXus, BIDS, and other formats](https://github.com/vig-os/fd5/issues/141)

### Description

Users evaluating fd5 will ask how it compares to existing scientific data formats. The whitepaper references NeXus conventions and Zarr-NGFF pyramids in passing but does not provide a direct comparison. A positioning document would help users understand when fd5 is the right choice and when another format is more appropriate.

Formats to compare against:

| Format | Overlap with fd5 |
|--------|-----------------|
| **Zarr / NGFF** | Chunked ND arrays, multiscale pyramids, cloud-native. Moving toward bioimaging standard. |
| **NeXus / HDF5** | HDF5-based, self-describing, established in neutron/synchrotron science. fd5 borrows conventions. |
| **BIDS** | Directory convention for neuroimaging with sidecar JSON metadata. |
| **NIfTI** | Single-file neuroimaging format, widely used but limited metadata. |
| **DICOM** | Universal medical imaging interchange format. The pain point fd5 was born from. |
| **RO-Crate** | Research object packaging with JSON-LD metadata. fd5 exports to this. |

The document should be factual and honest — acknowledging where other formats are stronger and where fd5 offers something different (immutability, content hashing, provenance DAG, embedded schema, single-file-per-product).

### Documentation Type

Add new documentation

### Target Files

- `docs/comparison.md` (new)

### Related Code Changes

None — this is a standalone document. May reference the whitepaper for design rationale.

### Acceptance Criteria

- [ ] Document covers at least Zarr, NeXus, BIDS, NIfTI, and DICOM
- [ ] Each comparison includes: what the format is, where it overlaps with fd5, where it diverges, and when to prefer one over the other
- [ ] Tone is neutral and factual — no marketing language
- [ ] Document is linked from the README or docs index
- [ ] Document acknowledges fd5's limitations (single-file model, no streaming writes, HDF5 dependency)

### Changelog Category

Added
