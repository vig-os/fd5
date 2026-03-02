---
type: issue
state: closed
created: 2026-02-25T01:07:43Z
updated: 2026-02-25T02:35:49Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/14
comments: 1
labels: feature, effort:large, area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:55.958Z
---

# [Issue 14]: [[FEATURE] Implement Merkle tree hashing and content_hash computation](https://github.com/vig-os/fd5/issues/14)

### Description

Implement the `fd5.hash` module: `id` computation, per-chunk hashing, Merkle tree construction, `content_hash` computation, and integrity verification.

This is the most complex core module. It must produce deterministic hashes from HDF5 file contents using the streaming workflow described in the whitepaper.

### Acceptance Criteria

- [ ] `compute_id(inputs, id_inputs_desc) -> str` computes `sha256:...` from identity inputs with `\0` separator
- [ ] `ChunkHasher` computes per-chunk SHA-256 hashes during streaming writes
- [ ] `MerkleTree` accumulates group/dataset/attr hashes bottom-up
- [ ] `content_hash` attr is excluded from the Merkle tree (no circular dependency)
- [ ] `_chunk_hashes` companion datasets are excluded from the Merkle tree
- [ ] Keys are sorted for deterministic traversal
- [ ] Row-major byte order (`tobytes()`) for chunk hashing
- [ ] `verify(path) -> bool` recomputes Merkle tree and compares with stored `content_hash`
- [ ] Same data + same attrs always produces same hash regardless of HDF5 internal layout
- [ ] Optional per-chunk hash companion datasets for large datasets
- [ ] ≥ 90% test coverage

### Dependencies

- Depends on #12 (`h5io`) for attr serialization consistency

### References

- Epic: #11
- Design: [DES-001 § fd5.hash](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5hash--hashing-and-integrity)
- Whitepaper: [§ content_hash computation](white-paper.md#content_hash-computation----merkle-tree-with-per-chunk-hashing)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:35 AM_

Completed — merged into dev.

