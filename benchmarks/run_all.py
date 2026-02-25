"""Run all fd5 benchmarks and print a summary table."""

from __future__ import annotations

import sys
import time

from benchmarks import bench_create, bench_hash, bench_manifest, bench_validate

HEADER = (
    f"{'Benchmark':<24} {'Parameter':<14} {'Mean (s)':<12} "
    f"{'StDev (s)':<12} {'Min (s)':<12} {'Max (s)':<12} {'Extra':<16}"
)
SEP = "-" * len(HEADER)


def _extra(row: dict) -> str:
    if "throughput_mb_s" in row:
        return f"{row['throughput_mb_s']:.1f} MB/s"
    if "per_file_ms" in row:
        return f"{row['per_file_ms']:.2f} ms/file"
    return ""


def main() -> None:
    wall_start = time.perf_counter()

    print("Running fd5 benchmarks...\n")

    all_results: list[dict] = []

    modules = [
        ("bench_create", bench_create),
        ("bench_hash", bench_hash),
        ("bench_validate", bench_validate),
        ("bench_manifest", bench_manifest),
    ]

    for name, mod in modules:
        print(f"  {name} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        results = mod.run()
        elapsed = time.perf_counter() - t0
        print(f"done ({elapsed:.1f}s)")
        all_results.extend(results)

    wall_elapsed = time.perf_counter() - wall_start

    print(f"\n{'=' * len(HEADER)}")
    print("fd5 Benchmark Summary")
    print(f"{'=' * len(HEADER)}\n")
    print(HEADER)
    print(SEP)

    for row in all_results:
        print(
            f"{row['benchmark']:<24} "
            f"{row['parameter']:<14} "
            f"{row['mean_s']:<12.4f} "
            f"{row['stdev_s']:<12.4f} "
            f"{row['min_s']:<12.4f} "
            f"{row['max_s']:<12.4f} "
            f"{_extra(row):<16}"
        )

    print(SEP)
    print(f"\nTotal wall time: {wall_elapsed:.1f}s")


if __name__ == "__main__":
    sys.exit(main() or 0)
