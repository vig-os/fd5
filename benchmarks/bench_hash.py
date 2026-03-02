"""Benchmark compute_content_hash() for various file sizes."""

from __future__ import annotations

import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from fd5.hash import compute_content_hash

SIZES_MB = [1, 10, 100, 1000]
REPEATS = 5
FLOAT32_BYTES = 4


def _create_h5(size_mb: int, path: Path) -> None:
    n_elements = (size_mb * 1024 * 1024) // FLOAT32_BYTES
    data = np.random.default_rng(42).standard_normal(n_elements, dtype=np.float32)
    with h5py.File(path, "w") as f:
        f.attrs["name"] = "bench"
        f.attrs["product"] = "bench"
        f.create_dataset("volume", data=data, chunks=True)


def _bench_hash(size_mb: int, repeats: int) -> list[float]:
    with tempfile.TemporaryDirectory() as tmp:
        h5_path = Path(tmp) / "bench.h5"
        _create_h5(size_mb, h5_path)
        timings: list[float] = []
        for _ in range(repeats):
            with h5py.File(h5_path, "r") as f:
                t0 = time.perf_counter()
                compute_content_hash(f)
                elapsed = time.perf_counter() - t0
            timings.append(elapsed)
    return timings


def run() -> list[dict[str, Any]]:
    """Run all hash benchmarks and return structured results."""
    results: list[dict[str, Any]] = []
    for size_mb in SIZES_MB:
        timings = _bench_hash(size_mb, REPEATS)
        throughput = (
            size_mb / statistics.mean(timings) if statistics.mean(timings) > 0 else 0
        )
        results.append(
            {
                "benchmark": "compute_content_hash",
                "parameter": f"{size_mb} MB",
                "mean_s": statistics.mean(timings),
                "stdev_s": statistics.stdev(timings) if len(timings) > 1 else 0.0,
                "min_s": min(timings),
                "max_s": max(timings),
                "throughput_mb_s": throughput,
                "repeats": REPEATS,
            }
        )
    return results


def main() -> None:
    print(
        f"{'Size':<10} {'Mean (s)':<12} {'StDev (s)':<12} "
        f"{'Min (s)':<12} {'Max (s)':<12} {'MB/s':<10}"
    )
    print("-" * 68)
    for row in run():
        print(
            f"{row['parameter']:<10} "
            f"{row['mean_s']:<12.4f} "
            f"{row['stdev_s']:<12.4f} "
            f"{row['min_s']:<12.4f} "
            f"{row['max_s']:<12.4f} "
            f"{row['throughput_mb_s']:<10.1f}"
        )


if __name__ == "__main__":
    main()
