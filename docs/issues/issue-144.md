---
type: issue
state: open
created: 2026-02-25T22:37:30Z
updated: 2026-02-26T01:04:15Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/144
comments: 0
labels: feature, effort:large, epic, area:core
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:45.055Z
---

# [Issue 144]: [[EPIC] Multi-language fd5 bindings](https://github.com/vig-os/fd5/issues/144)

### Description

fd5's core value is the HDF5 file itself — a self-describing, language-agnostic format. The Python library is the reference implementation, but researchers and instrument pipelines use many languages. Providing native bindings in other languages expands fd5's reach and fulfills the white paper's promise that "any tool can understand the file without domain-specific code."

This epic tracks the work to deliver fd5 reader/writer libraries in additional languages, all producing and consuming the same fd5 HDF5 files as the Python reference implementation.

### Motivation

- **Performance-critical pipelines** (detector readout, real-time ingest) need low-overhead writers (Rust, C/C++)
- **Scientific computing communities** (Julia, R) need native packages to read fd5 products without a Python intermediary
- **Web-based visualization** needs a browser-side reader (TypeScript/WASM) for client-side fd5 file inspection
- **Instrument firmware/embedded systems** need a minimal C library to write valid fd5 files at the source

### Prerequisites

- [ ] #154 — Extract fd5 format specification as a standalone language-neutral document
- [ ] #155 — Cross-language conformance test suite for fd5 format

### Sub-issues

- [ ] #145 — Rust fd5 crate — core read/write library
- [ ] #146 — Julia fd5 package — native reader/writer
- [ ] #147 — C/C++ fd5 library — minimal writer for instrument pipelines
- [ ] #148 — TypeScript/WASM fd5 reader — browser-side file inspection

### Acceptance Criteria

- Each language binding can read and write fd5 files that pass the conformance test suite
- Files produced by any binding are readable by all other bindings and the Python reference implementation
- Each binding has documentation, CI, and published packages for its ecosystem
