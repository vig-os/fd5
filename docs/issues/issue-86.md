---
type: issue
state: closed
created: 2026-02-25T07:20:22Z
updated: 2026-02-25T07:51:58Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/86
comments: 1
labels: none
assignees: gerchowl
milestone: Phase 5: Ecosystem & Tooling
projects: none
relationship: none
synced: 2026-02-26T04:15:54.310Z
---

# [Issue 86]: [[FEATURE] Integrate streaming chunk hashing into fd5.create() write path](https://github.com/vig-os/fd5/issues/86)

### Description

Currently `Fd5Builder._seal()` in `src/fd5/create.py` computes the content hash via a second-pass read-back using `compute_content_hash()`. The `ChunkHasher` class in `src/fd5/hash.py:41-63` exists but is not integrated into the write flow. For large files (>1 GB), data is written then re-read entirely for hashing.

### Tasks

- [ ] Integrate `ChunkHasher` into `Fd5Builder` for inline chunk hashing during writes
- [ ] Store `_chunk_hashes` dataset alongside each chunked dataset (per white-paper)
- [ ] Compute `MerkleTree` from inline hashes in `_seal()` instead of re-reading
- [ ] Fall back to second-pass for non-chunked datasets
- [ ] Maintain backward compatibility: identical `content_hash` either way

### Acceptance Criteria

- [ ] `content_hash` identical whether inline or second-pass
- [ ] `_chunk_hashes` datasets present for chunked datasets
- [ ] No test regressions, >= 95% coverage on modified code

### References

- White-paper § Design Principle 12
- DES-001 § hash.py: ChunkHasher
- Spike: #24 (PR #29)
- Audit: #81 | Epic: #85 | Refs: #10
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:51 AM_

Merged — implemented with tests.

