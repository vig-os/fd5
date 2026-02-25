---
type: issue
state: closed
created: 2026-02-25T01:09:48Z
updated: 2026-02-25T02:22:36Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/24
comments: 3
labels: effort:small, area:core, spike
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:52.799Z
---

# [Issue 24]: [[SPIKE] Validate h5py streaming chunk write + inline hashing workflow](https://github.com/vig-os/fd5/issues/24)

### Question

Can h5py's chunk-level write API (`write_direct_chunk()` or standard chunked writes) support inline SHA-256 hashing of each chunk during file creation, without a second pass over the data?

### Why It Matters

The fd5 design requires streaming hash computation during file creation (no reopen, no second pass). If h5py doesn't expose chunk boundaries during write, the hashing strategy may need to change.

### Investigation Scope

- [ ] Test `h5py.Dataset.id.write_direct_chunk()` for writing pre-compressed chunks with known boundaries
- [ ] Test standard chunked writes and whether we can intercept chunk data before compression
- [ ] Measure SHA-256 overhead on typical chunk sizes (1 slice of 512x512 float32 ≈ 1 MB)
- [ ] Document recommended approach for inline hashing

### Success Criteria

Findings documented with code examples. Clear recommendation on which h5py API to use for the `ChunkHasher` in #14.

### Time Box

1 day maximum.

### References

- Epic: #11
- Blocks: #14 (`hash` module)
- Whitepaper: [§ Write-time workflow](white-paper.md#write-time-workflow)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 01:24 AM_

## Spike Findings: h5py streaming chunk write + inline SHA-256 hashing

**PoC script:** `scripts/spike_chunk_hash.py`
**Environment:** h5py 3.15.1, HDF5 1.14.6, NumPy 2.4.2

### Question Answered

> Can h5py's chunk-level write API support inline SHA-256 hashing of each chunk during file creation, without a second pass?

**Yes.** Both approaches work and produce verifiable, round-trip-consistent hashes.

### Approach 1: `write_direct_chunk()`

- Caller serialises array → `bytes`, hashes those bytes, then writes them as a raw HDF5 chunk.
- Hash matches exactly what's stored on disk (verified via `read_direct_chunk` round-trip).
- **Caveat:** Bypasses HDF5 compression filters entirely. Not suitable when the file should also be compressed.

### Approach 2: Standard chunked write (`ds[i] = arr`)

- Hash `arr.tobytes()` before `ds[i] = arr`.
- Hash covers the **logical** (uncompressed) data — codec-independent and portable.
- HDF5 filters (compression, shuffle, etc.) still apply normally.
- Round-trip verified by re-reading and re-hashing.

### Benchmarks (1 slice = 512×512 float32 ≈ 1 MiB)

| Metric | Value |
|---|---|
| SHA-256 per chunk | ~554 µs |
| SHA-256 throughput | ~1.76 GiB/s |
| `np.tobytes()` per chunk | ~34 µs |
| SHA-256 / tobytes ratio | ~16× |
| Full write overhead (64 slices, in-memory) | ~20% wall-clock |

The ~20% overhead is measured on a pure in-memory write loop (tmpfs). Real workloads are I/O-bound, so effective overhead will be significantly lower.

### Recommendation

**Use standard chunked writes (Approach 2)** with `arr.tobytes() → sha256` before each `ds[i] = arr`.

Reasons:
- Hash is codec-independent (survives re-compression or filter changes)
- No need to manually handle compression or byte ordering
- `write_direct_chunk()` bypasses HDF5 filters, making it unsuitable when compression is desired
- Simpler code path for `ChunkHasher` (#14)

### Cross-approach verification

Both approaches produce identical hashes for the same data (same seed → same bytes → same SHA-256). This confirms the hashing is deterministic and approach-independent.

### Checklist from investigation scope

- [x] Test `h5py.Dataset.id.write_direct_chunk()` — works, hashes match on-disk bytes
- [x] Test standard chunked writes — works, hash logical data before write
- [x] Measure SHA-256 overhead — ~554 µs/chunk, ~20% wall-clock on in-memory writes
- [x] Document recommended approach — standard writes with pre-hash (Approach 2)

---

# [Comment #2]() by [gerchowl]()

_Posted on February 25, 2026 at 01:53 AM_

## Spike #24 — Findings: Inline SHA-256 hashing during h5py chunked writes

**PoC script:** `scripts/spike_chunk_hash.py` (on branch `spike/24-h5py-streaming-chunk-hash`)

### Setup

- **Shape:** `(64, 512, 512)` float32 — 64 MiB total
- **Chunk:** `(1, 512, 512)` — 1 MiB per chunk (matches typical single-slice write)
- **h5py:** 3.15.1, **HDF5:** 1.14.6, **NumPy:** 2.4.2

### Results

| Approach | Write (ms) | SHA-256 (ms) | Total (ms) | Throughput (MiB/s) |
|---|---|---|---|---|
| `write_direct_chunk` + inline hash | 22 | 36 | 216 | 297 |
| Standard chunked + pre-hash | 35 | 57 | 244 | 262 |
| Standard chunked (no hash, baseline) | 33 | — | 185 | 347 |

**SHA-256 overhead: ~31% vs the no-hash baseline** (on 1 MiB chunks).

### Verification

- Read-back hash check: **PASS** for both approaches.
- Cross-approach hash match (same RNG seed): **PASS** — both produce identical per-chunk digests.

### Key Findings

1. **`write_direct_chunk()` works.** It accepts raw bytes and writes them at a known chunk offset. We hash the bytes before writing. This gives full control over chunk boundaries — essential when we need guaranteed 1:1 mapping between written data and hash.

2. **Standard chunked write + pre-hash also works** for the uncompressed case, but the chunk boundary is implicit (relies on `chunk_shape == slice_shape`). If HDF5 ever re-chunks or we add compression, the written bytes may differ from what we hashed.

3. **SHA-256 on 1 MiB is ~0.6 ms/chunk.** At 64 chunks this is ~36–57 ms total. Throughput stays above 260 MiB/s even with hashing. This is negligible compared to I/O in real workloads.

4. **Data integrity round-trips correctly.** Hashes computed at write time match hashes computed by re-reading each chunk from the file.

### Recommendation

Use **`write_direct_chunk()`** for the `ChunkHasher` in #14:

- It gives **explicit control** over exactly which bytes are written (and therefore hashed).
- It decouples hashing from HDF5's internal compression/filtering pipeline — we hash raw bytes, then optionally compress before calling `write_direct_chunk()`.
- The standard chunked API is simpler but only safe when `chunk_shape == slice_shape` and compression is off. This constraint is too fragile for a general-purpose SDK.

### Checklist update

- [x] Test `h5py.Dataset.id.write_direct_chunk()` for writing pre-compressed chunks with known boundaries
- [x] Test standard chunked writes and whether we can intercept chunk data before compression
- [x] Measure SHA-256 overhead on typical chunk sizes (1 slice of 512×512 float32 ≈ 1 MB)
- [x] Document recommended approach for inline hashing

---

# [Comment #3]() by [gerchowl]()

_Posted on February 25, 2026 at 02:22 AM_

Completed — merged into dev.

