---
type: issue
state: open
created: 2026-02-25T22:38:02Z
updated: 2026-02-25T22:38:02Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/146
comments: 0
labels: feature, effort:large, area:core
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:44.379Z
---

# [Issue 146]: [[FEATURE] Julia fd5 package — native reader/writer](https://github.com/vig-os/fd5/issues/146)

### Parent

Part of #144 — Multi-language fd5 bindings

### Description

Implement a Julia package (`FD5.jl`) that reads and writes fd5-compliant HDF5 files, giving the Julia scientific computing community native access to fd5 data products without a Python intermediary.

### Motivation

- **Scientific computing overlap**: fd5 targets researchers who increasingly use Julia for numerical work, especially in medical imaging, physics, and ML pipelines
- **Native arrays with metadata**: Julia's type system and `Unitful.jl` can represent fd5 datasets as typed arrays with physical units attached — a natural fit for fd5's `@units` / `@unitSI` convention
- **Performance**: Julia's JIT compilation and native HDF5 bindings (HDF5.jl) make it possible to read fd5 files with near-zero overhead

### Proposed Scope

#### Phase 1 — Read path
- Open fd5 files via `HDF5.jl`
- Navigate group/dataset tree following fd5 conventions
- Return datasets as Julia arrays with metadata (units, description, dtype)
- Read and validate `_schema` attribute
- Verify content hash
- Parse provenance DAG

#### Phase 2 — Write path
- Create fd5 files with required root attributes
- Write Julia arrays as HDF5 datasets with fd5-compliant attributes
- Embed schema, compute content hash, seal file
- Write provenance links

#### Phase 3 — Ecosystem integration
- `Unitful.jl` integration: datasets returned with physical units attached
- `DataFrames.jl` integration: tabular/event data returned as DataFrames
- Registration in Julia General registry

### Technical Notes

- Build on `HDF5.jl` (mature, well-maintained)
- Use `JSON3.jl` + `JSONSchema.jl` for schema handling
- Use `SHA.jl` for content hashing
- Follow Julia package conventions (Project.toml, test/, docs/)

### Acceptance Criteria

- [ ] Julia package reads any fd5 file produced by the Python reference implementation
- [ ] Julia package writes fd5 files that the Python reference implementation can read and validate
- [ ] Passes the cross-language conformance test suite (#144)
- [ ] Registered in Julia General registry
- [ ] Documentation via Documenter.jl

### Additional Context

- HDF5.jl: https://github.com/JuliaIO/HDF5.jl
- Unitful.jl: https://github.com/PainterQubits/Unitful.jl
