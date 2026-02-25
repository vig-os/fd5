"""Benchmark fd5.create() for files with 1 MB, 10 MB, and 100 MB datasets."""

from __future__ import annotations

import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from fd5.create import create
from fd5.registry import register_schema

SIZES_MB = [1, 10, 100, 1000]
REPEATS = 3
FLOAT32_BYTES = 4


class _BenchSchema:
    """Minimal schema for benchmarking fd5.create()."""

    product_type: str = "bench/create"
    schema_version: str = "1.0.0"

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "bench/create"},
                "name": {"type": "string"},
            },
            "required": ["_schema_version", "product", "name"],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {"product": "bench/create"}

    def write(self, target: Any, data: Any) -> None:
        target.create_dataset("volume", data=data, chunks=True)

    def id_inputs(self) -> list[str]:
        return ["product", "name", "timestamp"]


def _make_array(size_mb: int) -> np.ndarray:
    n_elements = (size_mb * 1024 * 1024) // FLOAT32_BYTES
    return np.random.default_rng(42).standard_normal(n_elements, dtype=np.float32)


def _bench_create(size_mb: int, repeats: int) -> list[float]:
    register_schema("bench/create", _BenchSchema())
    import fd5.registry as reg

    reg._ep_loaded = True

    data = _make_array(size_mb)
    timings: list[float] = []

    for _ in range(repeats):
        work_dir = Path(tempfile.mkdtemp())
        try:
            t0 = time.perf_counter()
            with create(
                work_dir,
                product="bench/create",
                name="bench",
                description="benchmark file",
                timestamp="2026-01-01T00:00:00Z",
            ) as builder:
                builder.write_product(data)
            elapsed = time.perf_counter() - t0
            timings.append(elapsed)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    return timings


def run() -> list[dict[str, Any]]:
    """Run all create benchmarks and return structured results."""
    results: list[dict[str, Any]] = []
    for size_mb in SIZES_MB:
        timings = _bench_create(size_mb, REPEATS)
        results.append(
            {
                "benchmark": "fd5.create",
                "parameter": f"{size_mb} MB",
                "mean_s": statistics.mean(timings),
                "stdev_s": statistics.stdev(timings) if len(timings) > 1 else 0.0,
                "min_s": min(timings),
                "max_s": max(timings),
                "repeats": REPEATS,
            }
        )
    return results


def main() -> None:
    print(
        f"{'Size':<10} {'Mean (s)':<12} {'StDev (s)':<12} {'Min (s)':<12} {'Max (s)':<12}"
    )
    print("-" * 58)
    for row in run():
        print(
            f"{row['parameter']:<10} "
            f"{row['mean_s']:<12.4f} "
            f"{row['stdev_s']:<12.4f} "
            f"{row['min_s']:<12.4f} "
            f"{row['max_s']:<12.4f}"
        )


if __name__ == "__main__":
    main()
