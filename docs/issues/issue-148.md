---
type: issue
state: open
created: 2026-02-25T22:38:32Z
updated: 2026-02-25T22:38:32Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/148
comments: 0
labels: feature, effort:medium, area:core
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:43.841Z
---

# [Issue 148]: [[FEATURE] TypeScript/WASM fd5 reader — browser-side file inspection](https://github.com/vig-os/fd5/issues/148)

### Parent

Part of #144 — Multi-language fd5 bindings

### Description

Implement a TypeScript package (`@fd5/reader`) that reads fd5-compliant HDF5 files in the browser via WebAssembly, enabling client-side file inspection, metadata browsing, and lightweight visualization without a server backend.

### Motivation

- **"Any tool can understand the file"**: the white paper promises that fd5 files are self-describing and universally readable — a browser-based reader makes this real for the widest possible audience
- **Zero-install inspection**: researchers, reviewers, and collaborators can drag-and-drop an fd5 file into a web page to inspect its structure, metadata, provenance, and preview data — no Python install required
- **Dashboard integration**: web-based data portals and lab dashboards can render fd5 file contents client-side, reducing server load

### Proposed Scope

#### Phase 1 — Core reader
- Open fd5 HDF5 files in the browser using `h5wasm` (HDF5 compiled to WebAssembly)
- Navigate group/dataset tree following fd5 conventions
- Read root attributes (`id`, `_schema`, `_type`, `_version`, `created`, `product_type`)
- Read dataset metadata (shape, dtype, units, description)
- Read small datasets into typed arrays
- Validate content hash

#### Phase 2 — Metadata & provenance viewer
- Parse and display embedded `_schema` (JSON Schema)
- Render provenance DAG as a navigable graph
- Display structured metadata (study, subject, protocol groups)
- Export metadata as JSON / YAML

#### Phase 3 — Data preview
- Slice-based preview of ND arrays (single 2D slice from a 3D volume)
- Tabular preview of compound datasets (first N rows)
- Histogram / spectrum preview using embedded precomputed artifacts
- Thumbnail display from embedded preview datasets

### Technical Notes

- Build on `h5wasm` (HDF5 compiled to WASM): https://github.com/usnistgov/h5wasm
- TypeScript with strict mode, ESM output
- Framework-agnostic core (plain TS), optional React component library
- Bundle size budget: core reader < 500KB gzipped (h5wasm is ~300KB)
- Published to npm as `@fd5/reader`

### Acceptance Criteria

- [ ] TypeScript package reads any fd5 file produced by the Python reference implementation
- [ ] Passes the cross-language conformance test suite (#144) (Node.js test runner)
- [ ] Demo web page: drag-and-drop fd5 file, browse structure, view metadata
- [ ] Published to npm
- [ ] Documentation with usage examples

### Additional Context

- h5wasm: https://github.com/usnistgov/h5wasm
- h5web (React HDF5 viewer): https://github.com/silx-kit/h5web — potential integration target
- Read-only scope is intentional; browser-side writing is a non-goal for Phase 1
