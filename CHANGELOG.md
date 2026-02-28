# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- **Cross-language conformance test suite** ([#155](https://github.com/vig-os/fd5/issues/155))
  - 6 canonical fixture generators: minimal, sealed, with-provenance, multiscale, tabular, complex-metadata
  - 3 invalid fixture generators: missing-id, bad-hash, no-schema
  - Expected-result JSON files defining the format contract for any language binding
  - 39 pytest conformance tests covering structure, hash verification, provenance, multiscale, tabular, metadata, schema validation, and negative tests
  - README documenting how to use the suite and add new cases

- **Preflight feedback and status dashboard for devc-remote** ([#149](https://github.com/vig-os/fd5/issues/149))
  - Each preflight check now prints a success/warning/error status line as it completes
  - New checks: container-already-running, runtime version, compose version, SSH agent forwarding
  - Summary dashboard printed before proceeding to compose up
  - `--yes`/`-y` flag to auto-accept interactive prompts
  - Path and repo URL feedback with auto-derived annotation
  - Interactive Reuse/Recreate/Abort prompt when a container is already running
  - SSH agent forwarding check improved to use `ssh-add -l`

- **HDF5 dict round-trip helpers** ([#12](https://github.com/vig-os/fd5/issues/12))
  - `dict_to_h5(group, d)` writes nested Python dicts as HDF5 attrs/sub-groups
  - `h5_to_dict(group)` reads HDF5 attrs and sub-groups back to a Python dict
  - Deterministic sorted-key layout; lossless type mapping for str, int, float, bool, lists, and nested dicts

- **Physical units convention helpers** ([#13](https://github.com/vig-os/fd5/issues/13))
  - `write_quantity(group, name, value, units, unit_si)` creates sub-groups with `value`, `units`, `unitSI` attrs
  - `read_quantity(group, name)` reads them back as a `(value, units, unit_si)` tuple
  - `set_dataset_units(dataset, units, unit_si)` sets units attrs on datasets

- **Merkle tree hashing and content_hash computation** ([#14](https://github.com/vig-os/fd5/issues/14))
  - `compute_id(inputs, desc)` computes SHA-256 identity hashes from key-value pairs
  - `ChunkHasher` for per-chunk SHA-256 accumulation during streaming writes
  - `MerkleTree` bottom-up hash of an HDF5 file for file-level integrity
  - `compute_content_hash(root)` and `verify(path)` for sealing and verification

- **JSON Schema embedding and validation** ([#15](https://github.com/vig-os/fd5/issues/15))
  - `embed_schema(file, schema_dict)` writes `_schema` JSON string attr at file root
  - `dump_schema(path)` extracts and parses the embedded schema
  - `validate(path)` validates file structure against its embedded JSON Schema (Draft 2020-12)
  - `generate_schema(product_type)` produces a JSON Schema document via the registry

- **Provenance group writers** ([#16](https://github.com/vig-os/fd5/issues/16))
  - `write_sources(file, sources)` creates `sources/` group with per-source sub-groups and HDF5 external links
  - `write_original_files(file, records)` creates `provenance/original_files` compound dataset
  - `write_ingest(file, tool, version, timestamp)` creates `provenance/ingest/` group

- **Product schema registry with entry-point discovery** ([#17](https://github.com/vig-os/fd5/issues/17))
  - `get_schema(product_type)` looks up registered schemas
  - `register_schema(product_type, schema)` for programmatic registration
  - `list_schemas()` returns all registered product-type strings
  - Auto-discovers schemas from `fd5.schemas` entry-point group

- **Filename generation utility** ([#18](https://github.com/vig-os/fd5/issues/18))
  - `generate_filename(product, id_hash, timestamp, descriptors)` produces deterministic fd5 filenames
  - Format: `YYYY-MM-DD_HH-MM-SS_<product>-<id8>.h5`

- **`fd5.create()` builder / context-manager API** ([#19](https://github.com/vig-os/fd5/issues/19))
  - Context manager that creates a sealed fd5 file with atomic rename on success
  - `Fd5Builder` with `write_metadata`, `write_sources`, `write_provenance`, `write_study`, `write_extra`, `write_product`
  - Auto-embeds schema, computes content hash, and validates required attrs on seal

- **TOML manifest generation and parsing** ([#20](https://github.com/vig-os/fd5/issues/20))
  - `build_manifest(directory)` scans `.h5` files and extracts root attrs
  - `write_manifest(directory, output_path)` writes `manifest.toml`
  - `read_manifest(path)` parses an existing `manifest.toml`

- **Project dependencies** ([#21](https://github.com/vig-os/fd5/issues/21))
  - Core: `h5py`, `numpy`, `jsonschema`, `tomli-w`, `click`
  - Optional `dev` and `science` extras in `pyproject.toml`

- **Recon product schema** ([#22](https://github.com/vig-os/fd5/issues/22))
  - `ReconSchema` for reconstructed image volumes (3D/4D/5D float32)
  - Multiscale pyramid generation, MIP projections (coronal/sagittal), dynamic frame support
  - Chunked gzip compression; affine transforms and dimension ordering

- **CLI commands** ([#23](https://github.com/vig-os/fd5/issues/23))
  - `fd5 validate` — validate schema and content_hash integrity
  - `fd5 info` — print root attributes and dataset shapes
  - `fd5 schema-dump` — extract and pretty-print embedded JSON Schema
  - `fd5 manifest` — generate `manifest.toml` from a directory of fd5 files

- **Streaming chunk write + inline hashing spike** ([#24](https://github.com/vig-os/fd5/issues/24))
  - Validated h5py streaming chunk write with inline SHA-256 hashing workflow

- **End-to-end integration test** ([#49](https://github.com/vig-os/fd5/issues/49))
  - Full create → validate → info → manifest round-trip test

### Fixed

- **CI lint job missing tool dependencies** ([#48](https://github.com/vig-os/fd5/issues/48))
  - Added pre-commit and linting tools to dev extras in `pyproject.toml`

### Changed

### Removed

### Security
