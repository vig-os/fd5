---
type: issue
state: open
created: 2026-02-25T22:38:17Z
updated: 2026-02-25T22:38:17Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/147
comments: 0
labels: feature, effort:large, area:core
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:44.116Z
---

# [Issue 147]: [[FEATURE] C/C++ fd5 library — minimal writer for instrument pipelines](https://github.com/vig-os/fd5/issues/147)

### Parent

Part of #144 — Multi-language fd5 bindings

### Description

Implement a C library (`libfd5`) with an optional C++ wrapper that can write (and optionally read) fd5-compliant HDF5 files. This targets embedded instrument pipelines, detector readout systems, and environments where Python is unavailable or too slow.

### Motivation

- **Instrument-level FAIR data**: synchrotron beamlines, medical scanners, particle detectors, and sequencing instruments often run C/C++ firmware or acquisition software — a C library lets them produce valid fd5 files at the source
- **Minimal footprint**: a C library with only HDF5 as a dependency can run on constrained systems where Python runtimes are impractical
- **Broad FFI surface**: C ABI is the universal FFI target — R, Fortran, Go, and other languages can call `libfd5` directly

### Proposed Scope

#### Phase 1 — Write path (C)
- Create a new fd5 file with required root attributes
- Write ND array datasets with specified dtype, chunking, and compression
- Write metadata attributes (strings, numerics, arrays)
- Set `@units` / `@unitSI` on datasets
- Compute and store content hash (SHA-256) at close time
- Minimal API: `fd5_create()`, `fd5_write_dataset()`, `fd5_set_attr()`, `fd5_seal()`, `fd5_close()`

#### Phase 2 — Read path (C)
- Open an fd5 file and enumerate groups/datasets
- Read dataset data into caller-provided buffers
- Read attributes
- Validate content hash

#### Phase 3 — C++ wrapper
- RAII wrappers (`fd5::File`, `fd5::Dataset`, `fd5::Group`)
- `std::span` / `std::vector` integration for dataset I/O
- Optional header-only layer on top of the C API

### Technical Notes

- Depends only on HDF5 C library (libhdf5) and a SHA-256 implementation (e.g., OpenSSL or a vendored minimal implementation)
- Build with CMake, export pkg-config and CMake find-module
- Target C11 / C++17
- Provide a static and shared library

### Acceptance Criteria

- [ ] C library writes fd5 files that the Python reference implementation can read and validate
- [ ] C library reads fd5 files produced by the Python reference implementation
- [ ] Passes the cross-language conformance test suite (#144)
- [ ] CMake build with install targets, pkg-config, and find-module
- [ ] API documentation via Doxygen
- [ ] Example programs: minimal writer, minimal reader

### Additional Context

- HDF5 C API: https://docs.hdfgroup.org/hdf5/develop/group___h5.html
- Could serve as the native core that the Rust crate (#145) wraps or replaces
