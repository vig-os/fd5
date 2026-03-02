# fd5 — FAIR Data on HDF5

`fd5` is a self-describing, FAIR-principled data format for scientific data products built on HDF5. It defines conventions for storing N-dimensional arrays, tabular event data, time series, histograms, and arbitrary scientific measurements alongside their full metadata, provenance, and schema — all inside a single, immutable HDF5 file per data product.

The format is **domain-agnostic by design**: the core conventions (schema, provenance DAG, units, hashing, metadata structure) apply to any domain that produces immutable data products. Domain-specific **product schemas** are layered on top.

See [`white-paper.md`](white-paper.md) for the full specification.

## Features

- **Self-describing files** — embedded JSON Schema, `description` attributes on every group/dataset, units convention (`@units` / `@unitSI`) for AI and human readability
- **Immutable, write-once** — files are sealed with a Merkle-tree content hash at creation time; integrity is verifiable at any point
- **FAIR compliance** — persistent identifiers, structured metadata, open format, full provenance chain
- **Context-manager API** — `fd5.create()` orchestrates file creation, schema embedding, hashing, and atomic rename in one call
- **Product schema registry** — extensible via Python entry points (`fd5.schemas` group); ships with `recon` (reconstructed image volumes)
- **Lossless dict ↔ HDF5 round-trip** — `dict_to_h5` / `h5_to_dict` for nested metadata
- **Physical units helpers** — `write_quantity` / `read_quantity` and `set_dataset_units` following NeXus/OpenPMD conventions
- **Provenance tracking** — `sources/` group with external links, `provenance/original_files` compound dataset, ingest metadata
- **TOML manifest** — scan a directory of `.h5` files and generate a `manifest.toml` index
- **Deterministic filenames** — `YYYY-MM-DD_HH-MM-SS_<product>-<id8>.h5`
- **CLI toolkit** — `fd5 validate`, `fd5 info`, `fd5 schema-dump`, `fd5 manifest`

## Installation

```bash
pip install fd5
```

With optional scientific extras:

```bash
pip install "fd5[science]"
```

For development:

```bash
pip install "fd5[dev]"
```

## Quickstart

### Python API

```python
import numpy as np
from fd5.create import create

with create(
    "output/",
    product="recon",
    name="patient-001-brain-pet",
    description="FDG-PET brain reconstruction",
    timestamp="2025-06-15T10:30:00+00:00",
) as builder:
    # Write product-specific data
    builder.write_product({
        "volume": np.random.rand(128, 128, 128).astype(np.float32),
        "affine": np.eye(4),
        "dimension_order": "ZYX",
        "reference_frame": "LPS",
        "description": "Reconstructed PET volume",
    })

    # Write metadata, provenance, study info
    builder.write_metadata({"scanner": "Siemens Biograph", "tracer": "FDG"})
    builder.write_provenance(
        original_files=[{"path": "raw/pet.dcm", "sha256": "abc...", "size_bytes": 1024}],
        ingest_tool="my-pipeline",
        ingest_version="1.0.0",
        ingest_timestamp="2025-06-15T10:30:00+00:00",
    )

# File is automatically sealed: schema embedded, content_hash computed, renamed
```

### CLI

```bash
# Validate schema + integrity
fd5 validate output/2025-06-15_10-30-00_recon-a1b2c3d4.h5

# Print root attributes and dataset shapes
fd5 info output/2025-06-15_10-30-00_recon-a1b2c3d4.h5

# Extract embedded JSON Schema
fd5 schema-dump output/2025-06-15_10-30-00_recon-a1b2c3d4.h5

# Generate manifest.toml for a directory of fd5 files
fd5 manifest output/
```

## Architecture

The architecture is defined in the [white paper](white-paper.md). Key design decisions:

- **HDF5 is the single source of truth** — all other representations (TOML, YAML, JSON-LD) are derived dumps
- **One file = one data product** — each gets its own sealed `.h5` file
- **`_type` + `_version`** for forward-compatible extensibility
- **Merkle-tree hashing** for file-level integrity verification
- **Entry-point registry** for pluggable product schemas

### Module layout

```
src/fd5/
├── __init__.py          # Package root
├── create.py            # fd5.create() builder / context manager
├── h5io.py              # dict ↔ HDF5 round-trip helpers
├── hash.py              # Merkle tree hashing, id computation, verify()
├── units.py             # Physical units convention helpers
├── schema.py            # JSON Schema embed / validate / dump / generate
├── registry.py          # Product schema registry (entry-point discovery)
├── provenance.py        # sources/ and provenance/ group writers
├── manifest.py          # TOML manifest generation and parsing
├── naming.py            # Deterministic filename generation
├── cli.py               # Click CLI (validate, info, schema-dump, manifest)
└── imaging/
    ├── __init__.py      # Medical imaging domain schemas
    └── recon.py         # Recon product schema (3D/4D/5D volumes)
```

## Development

### Prerequisites

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Setup

```bash
git clone https://github.com/vig-os/fd5.git
cd fd5
pip install -e ".[dev]"
```

### Running tests

```bash
pytest
```

### Project dependencies

Core: `h5py`, `numpy`, `jsonschema`, `tomli-w`, `click`

See [`pyproject.toml`](pyproject.toml) for the full dependency specification.

## License

See the project repository for license details.
