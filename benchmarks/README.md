# fd5 Performance Benchmarks

Standalone timing scripts for fd5 core operations. No external benchmark framework required.

## Prerequisites

Install fd5 in development mode from the repository root:

```bash
uv pip install -e ".[dev]"
```

## Running All Benchmarks

From the repository root:

```bash
python -m benchmarks.run_all
```

This runs every benchmark module and prints a summary table with mean, standard deviation, min, and max timings.

## Running Individual Benchmarks

Each script is self-contained and can be run directly:

```bash
python -m benchmarks.bench_create
python -m benchmarks.bench_hash
python -m benchmarks.bench_validate
python -m benchmarks.bench_manifest
```

## Benchmark Descriptions

### bench_create

Measures end-to-end `fd5.create()` time (open file, write dataset, compute hashes, seal) for 1 MB, 10 MB, and 100 MB
float32 datasets.

### bench_hash

Measures `compute_content_hash()` (Merkle tree walk over HDF5 file) for 1 MB, 10 MB, and 100 MB datasets.
Reports throughput in MB/s.

### bench_validate

Measures two operations on sealed fd5 files of 1 MB, 10 MB, and 100 MB:

- **schema.validate** — JSON Schema validation of root attributes against the embedded schema.
- **hash.verify** — full Merkle tree recomputation and comparison with stored `content_hash`.

### bench_manifest

Measures `build_manifest()` for directories containing 10 and 100 `.h5` files. Reports per-file cost in ms.

## Interpreting Results

- **Mean** — average across repeated runs (see `REPEATS` constant in each script).
- **StDev** — standard deviation; high values suggest I/O or system noise.
- **Min / Max** — best and worst observed times.
- **Extra** — throughput (MB/s) for hash benchmarks; per-file cost (ms/file) for manifest benchmarks.

All timings use `time.perf_counter()` for high-resolution wall-clock measurement. Temporary files are created in
the system temp directory and cleaned up after each run.
