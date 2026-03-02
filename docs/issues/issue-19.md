---
type: issue
state: closed
created: 2026-02-25T01:08:39Z
updated: 2026-02-25T02:48:39Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/19
comments: 1
labels: feature, effort:large, area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:54.327Z
---

# [Issue 19]: [[FEATURE] Implement fd5.create() builder / context-manager API](https://github.com/vig-os/fd5/issues/19)

### Description

Implement the `fd5.create` module: the `Fd5Builder` context-manager that orchestrates file creation. This is the primary public API of fd5 — it opens an HDF5 file, writes root attrs, delegates to product schemas, computes hashes inline, and seals the file on exit.

### Acceptance Criteria

- [ ] `fd5.create(path, product, **kwargs)` returns a context-manager (`Fd5Builder`)
- [ ] Builder writes common root attrs on entry: `product`, `name`, `description`, `timestamp`, `_schema_version`
- [ ] Builder provides methods: `write_metadata()`, `write_sources()`, `write_provenance()`, `write_study()`
- [ ] Builder delegates product-specific writes to the registered `ProductSchema`
- [ ] On `__exit__` (success): schema embedded, `id` computed, `content_hash` computed, file sealed
- [ ] On `__exit__` (exception): incomplete file is deleted — no partial fd5 files on disk
- [ ] `study/` group written with license, creators, type, description
- [ ] `extra/` group support for unvalidated data
- [ ] Missing required attrs raise `Fd5ValidationError` before sealing
- [ ] Unknown product type raises `ValueError` with list of known types
- [ ] ≥ 90% test coverage

### Dependencies

- Depends on #12 (`h5io`), #13 (`units`), #14 (`hash`), #15 (`schema`), #16 (`provenance`), #17 (`registry`), #18 (`naming`)
- This is the integration point — all other core modules must exist first

### References

- Epic: #11
- Design: [DES-001 § fd5.create](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5create--file-builder)
- Whitepaper: [§ Immutability and write-once semantics](white-paper.md#13-immutability-and-write-once-semantics)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:48 AM_

Completed — merged into dev.

