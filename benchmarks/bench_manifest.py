"""Benchmark manifest generation for directories with 10 and 100 fd5 files."""

from __future__ import annotations

import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from fd5.h5io import dict_to_h5
from fd5.manifest import build_manifest

FILE_COUNTS = [10, 100]
REPEATS = 3


def _populate_dir(directory: Path, n_files: int) -> None:
    for i in range(n_files):
        path = directory / f"product-{i:04d}.h5"
        with h5py.File(path, "w") as f:
            dict_to_h5(
                f,
                {
                    "_schema_version": 1,
                    "product": "bench",
                    "id": f"sha256:{i:064d}",
                    "id_inputs": "product + name",
                    "name": f"file-{i}",
                    "description": f"Benchmark file {i}",
                    "content_hash": f"sha256:{i:064x}",
                    "timestamp": "2026-01-01T00:00:00Z",
                },
            )
            data = np.zeros(64, dtype=np.float32)
            f.create_dataset("volume", data=data)
            if i == 0:
                g = f.create_group("study")
                g.attrs["type"] = "benchmark"


def _bench_manifest(n_files: int, repeats: int) -> list[float]:
    work_dir = Path(tempfile.mkdtemp())
    try:
        _populate_dir(work_dir, n_files)
        timings: list[float] = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            build_manifest(work_dir)
            elapsed = time.perf_counter() - t0
            timings.append(elapsed)
        return timings
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run() -> list[dict[str, Any]]:
    """Run all manifest benchmarks and return structured results."""
    results: list[dict[str, Any]] = []
    for n_files in FILE_COUNTS:
        timings = _bench_manifest(n_files, REPEATS)
        per_file = statistics.mean(timings) / n_files if n_files > 0 else 0
        results.append(
            {
                "benchmark": "build_manifest",
                "parameter": f"{n_files} files",
                "mean_s": statistics.mean(timings),
                "stdev_s": statistics.stdev(timings) if len(timings) > 1 else 0.0,
                "min_s": min(timings),
                "max_s": max(timings),
                "per_file_ms": per_file * 1000,
                "repeats": REPEATS,
            }
        )
    return results


def main() -> None:
    print(
        f"{'Files':<12} {'Mean (s)':<12} {'StDev (s)':<12} "
        f"{'Min (s)':<12} {'Max (s)':<12} {'ms/file':<10}"
    )
    print("-" * 70)
    for row in run():
        print(
            f"{row['parameter']:<12} "
            f"{row['mean_s']:<12.4f} "
            f"{row['stdev_s']:<12.4f} "
            f"{row['min_s']:<12.4f} "
            f"{row['max_s']:<12.4f} "
            f"{row['per_file_ms']:<10.2f}"
        )


if __name__ == "__main__":
    main()
