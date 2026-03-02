#!/usr/bin/env python3
"""Spike #24 — Inline SHA-256 hashing during h5py chunked writes.

Tests two approaches:
  1. write_direct_chunk(): write pre-serialised chunks with known boundaries.
  2. Standard chunked writes with pre-hash of each chunk slice.

Measures SHA-256 overhead on a realistic chunk size (1 slice of 512×512 float32 ≈ 1 MB).

Usage:
    python scripts/spike_chunk_hash.py
"""

from __future__ import annotations

import hashlib
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROWS = 512
COLS = 512
NUM_SLICES = 64
DTYPE = np.float32
CHUNK_SHAPE = (1, ROWS, COLS)  # 1 slice per chunk ≈ 1 MiB
DATASET_SHAPE = (NUM_SLICES, ROWS, COLS)


@dataclass
class BenchResult:
    label: str
    write_s: float = 0.0
    hash_s: float = 0.0
    total_s: float = 0.0
    chunk_hashes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Approach 1: write_direct_chunk() with inline SHA-256
# ---------------------------------------------------------------------------
def approach_write_direct_chunk(path: Path) -> BenchResult:
    """Write raw (uncompressed) chunks via write_direct_chunk and hash each."""
    result = BenchResult(label="write_direct_chunk")
    rng = np.random.default_rng(42)

    t0 = time.perf_counter()
    with h5py.File(path, "w") as f:
        ds = f.create_dataset(
            "data",
            shape=DATASET_SHAPE,
            dtype=DTYPE,
            chunks=CHUNK_SHAPE,
            compression=None,
        )

        for i in range(NUM_SLICES):
            chunk = rng.standard_normal(CHUNK_SHAPE, dtype=DTYPE)
            raw = chunk.tobytes()

            t_h0 = time.perf_counter()
            digest = hashlib.sha256(raw).hexdigest()
            t_h1 = time.perf_counter()
            result.hash_s += t_h1 - t_h0
            result.chunk_hashes.append(digest)

            t_w0 = time.perf_counter()
            ds.id.write_direct_chunk((i, 0, 0), raw)
            t_w1 = time.perf_counter()
            result.write_s += t_w1 - t_w0

    result.total_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Approach 2: standard chunked write with pre-hash of each slice
# ---------------------------------------------------------------------------
def approach_standard_chunked(path: Path) -> BenchResult:
    """Write via normal slice assignment, hashing each slice before write."""
    result = BenchResult(label="standard_chunked (pre-hash)")
    rng = np.random.default_rng(42)

    t0 = time.perf_counter()
    with h5py.File(path, "w") as f:
        ds = f.create_dataset(
            "data",
            shape=DATASET_SHAPE,
            dtype=DTYPE,
            chunks=CHUNK_SHAPE,
            compression=None,
        )

        for i in range(NUM_SLICES):
            chunk = rng.standard_normal(CHUNK_SHAPE, dtype=DTYPE)

            t_h0 = time.perf_counter()
            digest = hashlib.sha256(chunk.tobytes()).hexdigest()
            t_h1 = time.perf_counter()
            result.hash_s += t_h1 - t_h0
            result.chunk_hashes.append(digest)

            t_w0 = time.perf_counter()
            ds[i : i + 1, :, :] = chunk
            t_w1 = time.perf_counter()
            result.write_s += t_w1 - t_w0

    result.total_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Baseline: standard chunked write, NO hashing
# ---------------------------------------------------------------------------
def baseline_no_hash(path: Path) -> BenchResult:
    """Write via normal slice assignment, no hashing (baseline)."""
    result = BenchResult(label="standard_chunked (no hash)")
    rng = np.random.default_rng(42)

    t0 = time.perf_counter()
    with h5py.File(path, "w") as f:
        ds = f.create_dataset(
            "data",
            shape=DATASET_SHAPE,
            dtype=DTYPE,
            chunks=CHUNK_SHAPE,
            compression=None,
        )

        for i in range(NUM_SLICES):
            chunk = rng.standard_normal(CHUNK_SHAPE, dtype=DTYPE)

            t_w0 = time.perf_counter()
            ds[i : i + 1, :, :] = chunk
            t_w1 = time.perf_counter()
            result.write_s += t_w1 - t_w0

    result.total_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Verification: read back and re-hash to confirm data integrity
# ---------------------------------------------------------------------------
def verify_hashes(path: Path, expected: list[str]) -> bool:
    """Re-read each chunk and verify SHA-256 matches."""
    with h5py.File(path, "r") as f:
        ds = f["data"]
        for i, expected_hash in enumerate(expected):
            raw = ds[i : i + 1, :, :].tobytes()
            actual = hashlib.sha256(raw).hexdigest()
            if actual != expected_hash:
                print(f"  MISMATCH at slice {i}: {actual} != {expected_hash}")
                return False
    return True


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def print_report(results: list[BenchResult]) -> None:
    chunk_bytes = int(np.prod(CHUNK_SHAPE)) * np.dtype(DTYPE).itemsize
    total_bytes = chunk_bytes * NUM_SLICES
    total_mib = total_bytes / (1024 * 1024)

    print("=" * 72)
    print("Spike #24 — Inline SHA-256 hashing during h5py chunked writes")
    print(f"  Shape: {DATASET_SHAPE}  dtype={DTYPE.__name__}")
    print(f"  Chunk: {CHUNK_SHAPE}  ({chunk_bytes / 1024:.0f} KiB per chunk)")
    print(f"  Total: {NUM_SLICES} chunks, {total_mib:.1f} MiB")
    print("=" * 72)

    for r in results:
        hash_pct = (r.hash_s / r.total_s * 100) if r.total_s > 0 else 0
        throughput = total_mib / r.total_s if r.total_s > 0 else 0
        print(f"\n  {r.label}")
        print(f"    write:      {r.write_s * 1000:8.1f} ms")
        print(f"    SHA-256:    {r.hash_s * 1000:8.1f} ms  ({hash_pct:.1f}% of total)")
        print(f"    total:      {r.total_s * 1000:8.1f} ms")
        print(f"    throughput: {throughput:8.1f} MiB/s")

    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    results: list[BenchResult] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Approach 1: write_direct_chunk
        p1 = tmp / "direct_chunk.h5"
        r1 = approach_write_direct_chunk(p1)
        results.append(r1)

        # Approach 2: standard chunked with pre-hash
        p2 = tmp / "standard_chunked.h5"
        r2 = approach_standard_chunked(p2)
        results.append(r2)

        # Baseline: no hash
        p3 = tmp / "baseline.h5"
        r3 = baseline_no_hash(p3)
        results.append(r3)

        print_report(results)

        # Verify data integrity for hashed approaches
        print("\nVerification (read-back SHA-256 check):")
        # write_direct_chunk writes raw bytes; read-back via h5py slice
        # should yield identical bytes for uncompressed data.
        ok1 = verify_hashes(p1, r1.chunk_hashes)
        print(f"  write_direct_chunk:       {'PASS' if ok1 else 'FAIL'}")

        ok2 = verify_hashes(p2, r2.chunk_hashes)
        print(f"  standard_chunked:         {'PASS' if ok2 else 'FAIL'}")

        # Both approaches used same RNG seed — hashes must match
        hashes_match = r1.chunk_hashes == r2.chunk_hashes
        print(f"  cross-approach hash match: {'PASS' if hashes_match else 'FAIL'}")

    print("\nConclusion:")
    hash_overhead_pct = (r2.hash_s / r3.total_s * 100) if r3.total_s > 0 else 0
    print(f"  SHA-256 adds ~{hash_overhead_pct:.1f}% overhead vs no-hash baseline.")
    print("  write_direct_chunk gives explicit control over chunk boundaries.")
    print("  Standard chunked write + pre-hash is simpler and equally correct")
    print("  for uncompressed data when chunk shape == slice shape.")


if __name__ == "__main__":
    main()
