"""Benchmark fd5 validate (schema validation + content_hash verification)."""

from __future__ import annotations

import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from fd5.create import create
from fd5.hash import verify
from fd5.registry import register_schema
from fd5.schema import validate

SIZES_MB = [1, 10, 100]
REPEATS = 3
FLOAT32_BYTES = 4


class _BenchSchema:
    """Minimal schema for benchmarking validation."""

    product_type: str = "bench/validate"
    schema_version: str = "1.0.0"

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "bench/validate"},
                "name": {"type": "string"},
            },
            "required": ["_schema_version", "product", "name"],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {"product": "bench/validate"}

    def write(self, target: Any, data: Any) -> None:
        target.create_dataset("volume", data=data, chunks=True)

    def id_inputs(self) -> list[str]:
        return ["product", "name", "timestamp"]


def _make_array(size_mb: int) -> np.ndarray:
    n_elements = (size_mb * 1024 * 1024) // FLOAT32_BYTES
    return np.random.default_rng(42).standard_normal(n_elements, dtype=np.float32)


def _create_test_file(size_mb: int, work_dir: Path) -> Path:
    register_schema("bench/validate", _BenchSchema())
    import fd5.registry as reg

    reg._ep_loaded = True

    data = _make_array(size_mb)
    with create(
        work_dir,
        product="bench/validate",
        name="bench",
        description="benchmark file",
        timestamp="2026-01-01T00:00:00Z",
    ) as builder:
        builder.write_product(data)

    return next(work_dir.glob("*.h5"))


def _bench_schema_validate(h5_path: Path, repeats: int) -> list[float]:
    timings: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        validate(h5_path)
        elapsed = time.perf_counter() - t0
        timings.append(elapsed)
    return timings


def _bench_content_hash_verify(h5_path: Path, repeats: int) -> list[float]:
    timings: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = verify(h5_path)
        elapsed = time.perf_counter() - t0
        assert result is True, "verify() returned False — file may be corrupt"
        timings.append(elapsed)
    return timings


def run() -> list[dict[str, Any]]:
    """Run all validation benchmarks and return structured results."""
    results: list[dict[str, Any]] = []

    for size_mb in SIZES_MB:
        work_dir = Path(tempfile.mkdtemp())
        try:
            h5_path = _create_test_file(size_mb, work_dir)

            timings = _bench_schema_validate(h5_path, REPEATS)
            results.append(
                {
                    "benchmark": "schema.validate",
                    "parameter": f"{size_mb} MB",
                    "mean_s": statistics.mean(timings),
                    "stdev_s": statistics.stdev(timings) if len(timings) > 1 else 0.0,
                    "min_s": min(timings),
                    "max_s": max(timings),
                    "repeats": REPEATS,
                }
            )

            timings = _bench_content_hash_verify(h5_path, REPEATS)
            results.append(
                {
                    "benchmark": "hash.verify",
                    "parameter": f"{size_mb} MB",
                    "mean_s": statistics.mean(timings),
                    "stdev_s": statistics.stdev(timings) if len(timings) > 1 else 0.0,
                    "min_s": min(timings),
                    "max_s": max(timings),
                    "repeats": REPEATS,
                }
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    return results


def main() -> None:
    print(
        f"{'Benchmark':<20} {'Size':<10} {'Mean (s)':<12} "
        f"{'StDev (s)':<12} {'Min (s)':<12} {'Max (s)':<12}"
    )
    print("-" * 78)
    for row in run():
        print(
            f"{row['benchmark']:<20} "
            f"{row['parameter']:<10} "
            f"{row['mean_s']:<12.4f} "
            f"{row['stdev_s']:<12.4f} "
            f"{row['min_s']:<12.4f} "
            f"{row['max_s']:<12.4f}"
        )


if __name__ == "__main__":
    main()
