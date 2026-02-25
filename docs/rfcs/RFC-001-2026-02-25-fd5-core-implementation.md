# RFC-001: fd5 Core Implementation

| Field | Value |
|-------|-------|
| **Status** | `accepted` |
| **Date** | 2026-02-25 |
| **Author** | @gerchowl |
| **Issue** | #10 |

## Problem Statement

Scientific data — from medical imaging scanners, particle detectors, sequencing
instruments, automated lab equipment, and computational pipelines — typically
arrives as vendor-specific output: DICOMs with thousands of inconsistent tags,
proprietary binary formats, ad-hoc CSV/HDF5 layouts, and metadata scattered
across spreadsheets, lab notebooks, and emails.

Working with this data today involves:

1. **Fragile caching layers** — JSON/pickle manifests that corrupt, go stale, or
   can't serialize domain types.
2. **Repeated parsing overhead** — re-reading headers every session, recomputing
   derived quantities that should have been stored once.
3. **Scattered metadata** — acquisition parameters in one format, instrument
   settings in another, protocol details in a third, operator notes in emails.
4. **No precomputed artifacts** — every visualization requires loading full
   datasets from scratch.
5. **No machine-readable schema** — new collaborators, AI agents, and automated
   pipelines must reverse-engineer the data structure.
6. **No provenance chain** — which raw data produced this result? Which
   calibration was applied? Which pipeline version?
7. **Mutable state** — files modified in place, no integrity guarantee, no way to
   detect corruption or tampering.

These problems are universal across any domain that transforms raw instrument
output into analysis-ready data products.

**If we do nothing:** researchers continue to waste significant time on data
wrangling instead of science. Every new collaborator re-invents parsing logic.
AI-assisted analysis remains impractical without self-describing data. Data
integrity issues go undetected. Reproducing results requires tribal knowledge.

### The fd5 proposition

`fd5` addresses this by defining a FAIR-principled, self-describing, immutable
data format built on HDF5. One file per data product, write-once semantics,
embedded schema, content hashing, provenance DAG, and derived metadata exports
(manifest, datacite, RO-Crate).

A comprehensive whitepaper (`white-paper.md`) specifies the full format design.
**The repo currently has zero implementation code.** This RFC defines the problem
space and research context; subsequent inception phases will scope the MVP,
architect the system, and decompose work into actionable issues.

## Impact

### Stakeholders

| Role | Who | Concerns |
|------|-----|----------|
| **Decider** | @gerchowl | Full vision, medical imaging as proving ground, broad adoption |
| **Primary users** | Domain scientists, data engineers | Must be easy to ingest data and query metadata without HDF5 expertise |
| **Secondary users** | AI agents, automated pipelines | Must be able to discover and understand file structure programmatically |
| **Reviewers** | @irenecortinovis, @c-vigo | DataLad integration perspective, file signing, device data/Prometheus metrics |
| **Ecosystem** | HDF5/NeXus/Zarr communities | Interoperability, convention alignment |

### Severity

High. The whitepaper is complete and the design is mature, but there is no
implementation to validate or use. The project cannot attract contributors or
real-world testing without a working SDK.

## Prior Art & References

The whitepaper includes a comparison table. This section extends it with
additional research.

### Formats compared in the whitepaper

| Format | Strengths | Gaps fd5 addresses |
|--------|-----------|-------------------|
| **NeXus/HDF5** | Mature, `@units`, `default` chain, NXlog/NXsensor | Tied to neutron/X-ray facilities; fd5 adopts patterns selectively as domain-agnostic conventions |
| **OpenPMD** | `unitSI`, mesh/particle duality | Focused on particle-in-cell simulations; no general product schema extensibility |
| **BIDS** | Self-describing filenames, metadata inheritance | Tied to neuroimaging; filenames encode too much; no write-once integrity |
| **NIfTI** | Simple, widely supported for volumes | No metadata beyond affine; no provenance; no non-volume data |
| **DICOM** | Comprehensive tags, universal in clinical imaging | Verbose, inconsistent across vendors, poor for non-image data, mutable |
| **ROOT/TTree** | Excellent for event data, schema evolution | C++ ecosystem; poor Python ergonomics; no self-describing metadata conventions |
| **Zarr v3** | Cloud-native chunked storage, parallel I/O | Storage engine only; no metadata conventions, no provenance, no schema embedding |
| **OME-Zarr (NGFF)** | Multiscale pyramids, cloud-optimized bioimaging | Microscopy-focused; no event data, spectra, or calibration; no provenance DAG |
| **RO-Crate** | Standard for packaging research objects, Schema.org JSON-LD | Not a data storage format; fd5 generates RO-Crate as derived output |
| **RDF / Linked Data** | Web-scale semantic interoperability, SPARQL | Not a storage format; high complexity; fd5 bridges via RO-Crate export |

### Additional formats researched

| Format | What it is | Relevance to fd5 |
|--------|-----------|------------------|
| **MIDAS** | Data acquisition system (PSI/TRIUMF) for nuclear/particle physics. Uses a custom binary event format with bank-structured events, 16-byte event headers, and 4-char bank IDs. Written in C/C++, runs on Linux/macOS/Windows. Supports VME, CAMAC, GPIB, USB, fiber optic hardware. | MIDAS is an **upstream DAQ system**, not a data product format. fd5 would ingest MIDAS `.mid` files the same way it ingests DICOMs — parse, transform, store as clean fd5 products. Key difference: MIDAS events are mutable, append-oriented acquisition streams; fd5 products are immutable, sealed data products. MIDAS has no self-describing schema, no content hashing, no provenance DAG, no FAIR metadata. fd5's `listmode` and `spectrum` product schemas are natural targets for MIDAS event data after ingest. |
| **Apache Parquet** | Columnar storage format (Apache ecosystem). Excellent for tabular analytics — column pruning, predicate pushdown, dictionary/RLE encoding. Widely supported (Polars, DuckDB, Spark, Arrow). Immutable files. Schema embedded via Thrift. | Parquet excels at **tabular/columnar queries** (event tables, metadata catalogs) but has no concept of N-dimensional arrays, nested group hierarchies, embedded provenance, physical units, or self-describing schema for scientific data products. It could serve as a **complementary format** for metadata indexes or event table exports, but cannot replace HDF5 for the full fd5 use case (volumes, pyramids, mixed data types in one file). fd5 could optionally export event tables or manifest data to Parquet for analytics tooling. |
| **ASDF** | Advanced Scientific Data Format (astronomy). YAML header + binary data blocks in one file. JSON Schema validation. Python-native. Designed for JWST and astronomical data. | Closest philosophical cousin to fd5 — self-describing, schema-embedded, immutable-friendly. Key differences: ASDF uses YAML (not HDF5) as the container, lacks provenance DAG conventions, has no content hashing/Merkle tree, no multiscale pyramids, and is astronomy-specific. fd5's choice of HDF5 over YAML+binary gives better performance for large N-dimensional arrays and broader tool ecosystem support. |
| **NetCDF-4** | Built on HDF5. Self-describing, array-oriented. Standard in climate/weather/oceanography. CF conventions for metadata. | NetCDF-4 is essentially "HDF5 with conventions" — similar to what fd5 does but for geoscience. Key differences: NetCDF conventions (CF) are domain-specific to earth science; no write-once immutability guarantee; no content hashing; no provenance DAG; limited to array data (no compound tables, no polymorphic schemas). fd5 could potentially read NetCDF-4 files via h5py since they're HDF5 underneath. |

### Key insight from prior art

No existing format combines **all** of: (1) self-describing embedded schema,
(2) content-addressed immutability with Merkle tree, (3) structured provenance
DAG, (4) physical units on every field, (5) domain-agnostic product schema
extensibility, (6) FAIR metadata with RO-Crate/datacite export, and
(7) AI-readability via description attributes. fd5's value proposition is the
integration of these properties into a single coherent format, not any one
feature in isolation.

## Open Questions

### Assumptions

| # | Assumption | Risk level | Validation |
|---|-----------|------------|------------|
| A1 | HDF5 is the right container format (vs. Zarr, custom binary, SQLite) | Low | Whitepaper §HDF5 cloud compatibility argues this thoroughly; HDF5's single-file model, tool ecosystem, and SWMR support align with fd5's design goals |
| A2 | Write-once immutability is acceptable for all target use cases | Medium | Some workflows may want to append metadata post-creation (annotations, QC flags). Need to validate that "create new file" is always acceptable |
| A3 | JSON Schema is sufficient for schema embedding (vs. more expressive formats like OWL, Avro, Protocol Buffers) | Low | JSON Schema is human-readable, widely tooled, and sufficient for structural validation. Semantic reasoning is delegated to RO-Crate export layer |
| A4 | The `_type`/`_version` extensibility mechanism is enough for long-term schema evolution | Low-Medium | Works well for additive changes; breaking changes within a type require version bumps. Need to validate with real schema evolution scenarios |
| A5 | Domain scientists will adopt a new format if the tooling is good enough | High | Biggest adoption risk. Mitigation: zero-friction ingest from existing formats, immediate value (no more re-parsing), good CLI/Python API |
| A6 | Merkle tree hashing at write time has acceptable performance overhead | Low | SHA-256 throughput (~1 GB/s on modern CPUs) is fast relative to HDF5 I/O. Streaming hash design avoids double-pass |
| A7 | A Python-only SDK is sufficient for the initial implementation | Medium | Python covers the primary audience (scientists, data engineers). C/C++ or Rust bindings may be needed for high-throughput ingest pipelines later |
| A8 | Medical imaging (PET/CT) is a representative enough proving ground to validate the domain-agnostic core | Low | The medical imaging schemas exercise all structural archetypes (volumes, events, spectra, transforms, calibrations, ROIs, time series) |

### Dependencies

| Dependency | Type | Stability | Risk |
|-----------|------|-----------|------|
| `h5py` | Runtime | Mature, actively maintained | Low |
| `numpy` | Runtime (via h5py) | Mature | Low |
| `jsonschema` | Runtime | Stable, well-maintained | Low |
| `tomli-w` | Runtime | Small, stable | Low |
| `click` | Runtime | Stable, widely used | Low |
| HDF5 C library | Transitive (via h5py) | Mature | Low |

All dependencies are open source, offline-capable, and have no external API
requirements.

### Risks

| # | Risk | Severity | Likelihood | Mitigation |
|---|------|----------|------------|------------|
| R1 | **HDF5 limitations surface late** — e.g., cloud access latency, concurrent write needs, file size limits | High | Low | Whitepaper already addresses cloud trade-offs honestly; fd5 is designed for batch/local-first workflows. Monitor for edge cases |
| R2 | **Schema design errors** discovered after files are in production | High | Medium | Additive-only evolution policy limits blast radius. Migration tooling (`fd5.migrate`) is a core feature. Start with thorough schema review before v1 |
| R3 | **Adoption barrier** — format is too complex or requires too much upfront investment | High | Medium | Prioritize developer experience: good defaults, minimal boilerplate, excellent error messages, comprehensive examples. Make ingest from DICOM/MIDAS dead simple |
| R4 | **Scope creep** — trying to support every domain from day one dilutes focus | Medium | High | Medical imaging is the proving ground. Core is domain-agnostic; domain schemas are separate packages. Resist adding domain-specific features to core. Layered architecture (chosen approach) mitigates this structurally |
| R5 | **Performance** — Merkle tree computation, gzip compression, or HDF5 overhead makes write times unacceptable for high-throughput pipelines | Medium | Low | Benchmark early. Chunk hashing is optional for small datasets. Compression level is configurable. Profile before optimizing |
| R6 | **File signing** (requested in issue #1 comment) adds complexity to immutability model | Low | Medium | Treat as a future enhancement. Signing is orthogonal to content hashing — can be layered on top without changing the core format |
| R7 | **Dependency on h5py** — h5py maintenance, HDF5 C library compatibility, thread safety | Medium | Low | h5py is mature and actively maintained. Pin versions. Abstract HDF5 access behind an internal API to allow future backend swaps if needed |

## Proposed Solution

### Approach: Layered core + domain plugins

Build `fd5` as a small **core library** handling HDF5 conventions, metadata
helpers, hashing, schema embedding, provenance, and file creation — with
domain-specific **product schemas as separate packages** (e.g., `fd5-imaging`
for `recon`/`listmode`/`sinogram`). Export generators (manifest, datacite,
RO-Crate) live in core since they are domain-agnostic.

This matches the whitepaper's explicit architecture: "domain schemas are layered
on top of the core." Product schemas are defined schema-first (JSON Schema as
the source of truth for each product type), with the Python builder API
conforming to the schema.

### MVP scope (in)

| # | Capability | Detail |
|---|-----------|--------|
| 1 | `fd5.create()` builder API | Context-manager producing a sealed, immutable HDF5 file with streaming hash |
| 2 | `h5_to_dict` / `dict_to_h5` | Round-trip metadata helpers with full type mapping (see whitepaper §Implementation Notes) |
| 3 | Content hashing | File-level Merkle tree (`content_hash`), per-chunk hashing for large datasets |
| 4 | `id` computation | SHA-256 of identity inputs with `\0` separator, `id_inputs` attr |
| 5 | Schema embedding | `_schema` JSON attribute on root, `_schema_version` |
| 6 | Units convention | Sub-group pattern for attributes (`value`/`units`/`unitSI`), dataset attrs for datasets |
| 7 | Provenance conventions | `sources/` group with external links, `provenance/original_files` compound dataset |
| 8 | `study/` context group | Domain-agnostic study metadata (license, creators) |
| 9 | `extra/` group | Unvalidated collection support |
| 10 | File naming | `YYYY-MM-DD_HH-MM-SS_<product>-<id>_<descriptors>.h5` generation |
| 11 | Manifest generation | `manifest.toml` from a directory of fd5 files |
| 12 | Schema validation | Validate an fd5 file against its embedded schema |
| 13 | Product schema registration | Mechanism for domain packages to register product types |
| 14 | `recon` product schema | First domain schema (`fd5-imaging`): volumes, pyramids, MIPs, frames, affine |
| 15 | CLI | `fd5 validate`, `fd5 info`, `fd5 schema-dump`, `fd5 manifest` |

### Out of scope (deferred)

| Feature | Reason |
|---------|--------|
| `listmode`, `sinogram`, `sim`, `transform`, `calibration`, `spectrum`, `roi`, `device_data` schemas | Each is a separate unit of work; `recon` alone validates all core patterns |
| Datacite export (`datacite.yml`) | Lower priority than manifest; deferred to Phase 4 |
| RO-Crate export (`ro-crate-metadata.json`) | Requires Schema.org mapping layer; deferred to Phase 4 |
| `fd5.migrate()` tool | No existing files to migrate yet |
| Description quality validator (LLM/heuristic) | Nice-to-have; not needed for correctness |
| Non-Python SDKs (C/C++, Rust) | Python covers primary audience (A7) |
| Cloud/S3 access via ros3 VFD | Local-first is the design goal |
| Ingest pipelines (DICOM, MIDAS, etc.) | Explicitly out of scope per whitepaper |
| File signing | Orthogonal to content hashing (R6) |
| DataLad integration | External tool concern; fd5 provides hooks |

### Build vs buy

| Component | Decision | Rationale |
|-----------|----------|-----------|
| HDF5 I/O | **Use** `h5py` | Mature, standard Python HDF5 binding |
| Hashing | **Build** (thin wrapper over `hashlib`) | SHA-256 is stdlib; Merkle tree logic is fd5-specific |
| JSON Schema | **Use** `jsonschema` for validation | Standard, well-maintained |
| Schema generation | **Build** | fd5-specific structure; no existing tool fits |
| TOML manifest | **Use** `tomllib` (read, stdlib 3.11+) + `tomli-w` (write) | Small dependency for write only |
| CLI | **Use** `click` or stdlib `argparse` | Lightweight; click preferred for subcommands |
| NumPy arrays | **Use** `numpy` | Required by h5py; already in science stack |
| File naming | **Build** | Simple string formatting; fd5-specific convention |
| Units handling | **Build** | Thin convention layer; no library matches the sub-group pattern |

### Feasibility assessment

| Dimension | Assessment |
|-----------|-----------|
| **Technical** | All components use mature technology (HDF5, SHA-256, JSON Schema, Python). No novel algorithms. Whitepaper resolves all design questions. |
| **Resources** | Standard scientific Python expertise. Estimated 4–6 weeks focused development. No paid services; all dependencies are open source. |
| **Dependencies** | `h5py` (stable), `numpy` (stable, required by h5py), `jsonschema` (stable), `tomli-w` (small, stable). No external APIs; fully offline-capable. |

## Alternatives Considered

### Approach 1: Full-stack monolithic SDK

Build all 9 product schemas, hashing, schema embedding, manifest, datacite,
RO-Crate, validation, and CLI in a single package.

**Rejected because:** Long time to first usable release. Schema changes in one
domain affect the whole package. High scope-creep risk (R4). Harder to attract
contributors since the codebase is large from day one.

### Approach 3: Schema-first, code-generated SDK

Define JSON Schemas for all product types first, then generate the Python SDK
(builder API, validators, type stubs) from the schemas.

**Partially adopted:** Schema-first design principles inform how product schemas
are defined (JSON Schema is the source of truth). Full code generation rejected
because it adds build-step complexity and debugging indirection, and generated
code may not feel Pythonic. The chosen approach writes the builder API by hand
but validates it against the schema.

### Approach 4: Minimal write API + reference files

Build only a thin write API plus reference example files. No read helpers, no
exports, no CLI.

**Rejected because:** Too minimal for adoption. No validation on read, no
derived outputs, no schema embedding automation. Users must understand HDF5
deeply, violating the low-barrier-to-entry goal (A5).

## Phasing

### Phase 1 — Core SDK

- `h5_to_dict` / `dict_to_h5` with full type mapping
- Units convention helpers
- `fd5.create()` builder/context-manager API
- Streaming Merkle tree hash computation (`content_hash`)
- `id` computation
- Schema embedding (`_schema` JSON attribute)
- Schema validation
- Provenance conventions (`sources/`, `provenance/`)
- `study/` and `extra/` group support
- File naming utility
- Product schema registration mechanism
- **Deliverable:** `fd5` core package that can create and validate generic fd5
  files

### Phase 2 — First Domain Schema + CLI

- `recon` product schema (volumes, pyramids, MIPs, frames, affine)
- CLI: `fd5 validate`, `fd5 info`, `fd5 schema-dump`
- Manifest generation (`manifest.toml`)
- CLI: `fd5 manifest`
- **Deliverable:** End-to-end workflow: create a recon file → validate it →
  generate manifest

### Phase 3 — Remaining Medical Imaging Schemas

- `listmode`, `sinogram`, `sim`, `transform`, `calibration`, `spectrum`, `roi`,
  `device_data`
- Each as part of `fd5-imaging` domain package
- **Deliverable:** Complete medical imaging domain coverage

### Phase 4 — FAIR Export Layer

- RO-Crate JSON-LD generation (`ro-crate-metadata.json`)
- Datacite metadata generation (`datacite.yml`)
- Schema dump to standalone JSON file
- **Deliverable:** Full FAIR metadata export pipeline

### Phase 5 — Ecosystem & Tooling

- `fd5.migrate()` for schema version upgrades
- Description quality validation
- Performance benchmarks
- DataLad integration hooks
- Additional domain schema packages (genomics, remote sensing, etc.)

## Success Criteria

| Criterion | Measurement |
|-----------|-------------|
| A valid `recon` fd5 file can be created | `fd5.create()` produces a file that passes `fd5 validate` |
| Self-describing | `h5dump -A` of any fd5 file produces a complete, human-readable manifest |
| Content integrity | `content_hash` matches on re-verification; corruption is detected |
| Round-trip metadata | `h5_to_dict(dict_to_h5(d)) == d` for all supported Python types |
| Schema embedded | `_schema` attribute is valid JSON Schema; file validates against it |
| Provenance tracked | `sources/` links resolve; `provenance/original_files` hashes verify |
| Manifest generated | `fd5 manifest <dir>` produces correct `manifest.toml` from a set of fd5 files |
| Domain extensibility | A new product type can be registered without modifying `fd5` core |
| Test coverage | ≥ 90% line coverage on core library |
| Documentation | README with quickstart; API docstrings on all public functions |

## Implementation Tracking

- Design: [DES-001](../designs/DES-001-2026-02-25-fd5-sdk-architecture.md)

### Phase 1: Core SDK — COMPLETE

Epic: #11 (closed) | Milestone: Phase 1: Core SDK

| Issue | Module | Status | Tests | Coverage |
|-------|--------|--------|-------|----------|
| #21 | Dependencies + CLI scaffold | Merged (PR #25) | CLI verified | N/A |
| #12 | `fd5.h5io` | Merged (PR #31) | 38 pass | 97% |
| #13 | `fd5.units` | Merged (PR #33) | 13 pass | 100% |
| #14 | `fd5.hash` | Merged (PR #40) | 36 pass | 95% |
| #15 | `fd5.schema` | Merged (PR #41) | 16 pass | 100% |
| #16 | `fd5.provenance` | Merged (PR #37) | 25 pass | 100% |
| #17 | `fd5.registry` | Merged (PR #35) | 10 pass | 100% |
| #18 | `fd5.naming` | Merged (PR #28) | 9 pass | 100% |
| #19 | `fd5.create` | Merged (PR #46) | 198 pass (full suite) | — |
| #20 | `fd5.manifest` | Merged (PR #39) | 23 pass | 100% |
| #24 | [SPIKE] Chunk hashing | Merged (PR #29) | PoC script | N/A |

### Phase 2: Recon Schema + CLI — COMPLETE

Milestone: Phase 2: Recon Schema + CLI

| Issue | Module | Status | Tests | Coverage |
|-------|--------|--------|-------|----------|
| #22 | `fd5_imaging.recon` | Merged (PR #45) | 222 pass (full suite) | — |
| #23 | `fd5.cli` | Merged (PR #47) | 201 pass (full suite) | — |
| #49 | Integration tests | Merged (PR #62) | 20 e2e tests | — |
| #48 | CI: add pre-commit deps | Merged (PR #50) | — | — |
| #63 | CI: vig-utils hooks | In progress | — | — |
| #65 | README + CHANGELOG | In progress | — | — |

### Phase 3: Medical Imaging Schemas — COMPLETE

Epic: #61 | Milestone: Phase 3: Medical Imaging Schemas

| Issue | Schema | Status | Tests |
|-------|--------|--------|-------|
| #51 | `fd5.imaging.listmode` | Implemented | `test_listmode.py` |
| #52 | `fd5.imaging.sinogram` | Implemented | `test_sinogram.py` |
| #53 | `fd5.imaging.sim` | Implemented | `test_sim.py` |
| #54 | `fd5.imaging.transform` | Implemented | `test_transform.py` |
| #55 | `fd5.imaging.calibration` | Implemented | `test_calibration.py` |
| #56 | `fd5.imaging.spectrum` | Implemented | `test_spectrum.py` |
| #57 | `fd5.imaging.roi` | Implemented | `test_roi.py` |
| #58 | `fd5.imaging.device_data` | Implemented | `test_device_data.py` |

All 9 schemas registered via entry points in `pyproject.toml`. Full suite: 791 tests passing.

### Phase 4: FAIR Export Layer — COMPLETE

Milestone: Phase 4: FAIR Export Layer

| Issue | Module | Status | Tests |
|-------|--------|--------|-------|
| #59 | `fd5.rocrate` (RO-Crate JSON-LD) | Implemented | `test_rocrate.py` |
| #60 | `fd5.datacite` (DataCite YAML) | Implemented | `test_datacite.py` |

CLI commands `fd5 rocrate` and `fd5 datacite` added. See audit on #81 for deviations.
