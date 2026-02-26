---
type: issue
state: open
created: 2026-02-25T22:37:51Z
updated: 2026-02-25T22:37:51Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/145
comments: 0
labels: feature, effort:large, area:core
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:44.751Z
---

# [Issue 145]: [[FEATURE] Rust fd5 crate — core read/write library](https://github.com/vig-os/fd5/issues/145)

### Parent

Part of #144 — Multi-language fd5 bindings

### Description

Implement a Rust crate (`fd5`) that can read and write fd5-compliant HDF5 files, providing a high-performance, memory-safe foundation that can also serve as a shared native core for other language bindings via C ABI / FFI.

### Motivation

- **Performance**: zero-copy memory-mapped reads, safe concurrency for SWMR workloads, and compiled-speed hashing / schema validation
- **FFI foundation**: a Rust crate with a C ABI can be called from Python (PyO3/cffi), Julia (ccall), R (.Call), and C++ — potentially replacing hot paths in the Python implementation
- **Instrument pipelines**: compiled binaries for high-throughput ingest (detector readout, streaming acquisitions)

### Proposed Scope

#### Phase 1 — Read path
- Open an fd5 HDF5 file and navigate the group/dataset tree
- Read root attributes (`id`, `_schema`, `_type`, `_version`, `created`, `product_type`)
- Read dataset data into ndarray with dtype preservation
- Read `@units` / `@unitSI` attributes
- Validate content hash against stored hash
- Traverse provenance DAG (`sources/` group)

#### Phase 2 — Write path
- Create a new fd5 file with required root attributes
- Write ND array datasets with chunking and compression
- Write metadata groups and attributes
- Embed JSON Schema as `_schema` attribute
- Compute and seal content hash at close time
- Write provenance links

#### Phase 3 — FFI layer
- Expose a C-compatible API (`libfd5`) for cross-language consumption
- Python bindings via PyO3 (optional feature)
- Benchmark against pure-Python fd5 for read/write throughput

### Technical Notes

- Use the `hdf5-rust` crate (or `hdf5-sys` for lower-level control)
- Use `ndarray` for array types
- Use `serde` + `jsonschema` for schema validation
- Target `no_std`-compatible core where feasible for embedded use

### Acceptance Criteria

- [ ] Rust crate reads any fd5 file produced by the Python reference implementation
- [ ] Rust crate writes fd5 files that the Python reference implementation can read and validate
- [ ] Passes the cross-language conformance test suite (#144)
- [ ] Published to crates.io with docs on docs.rs
- [ ] Benchmark results comparing Rust vs Python read/write throughput

### Additional Context

- Complements #143 (benchmarking spike) — Rust implementation provides a performance baseline
- Rust's `hdf5` crate: https://github.com/aldanor/hdf5-rust
