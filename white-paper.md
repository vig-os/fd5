# fd5 -- FAIR Data on HDF5

## Abstract

`fd5` is a self-describing, FAIR-principled data format for scientific data products built on HDF5. It defines conventions for storing N-dimensional arrays, tabular event data, time series, histograms, and arbitrary scientific measurements alongside their full metadata, provenance, and schema -- all inside a single, immutable HDF5 file per data product.

The format is designed for **write-once, read-many (SWMR)** workloads: a data product is created once by an ingest or processing pipeline, sealed with a content hash, and never modified. This immutability guarantee simplifies caching, integrity verification, provenance tracking, and concurrent read access.

The HDF5 file is the **single source of truth**. Every other representation (TOML manifests, YAML metadata exports, datacite records, RO-Crate JSON-LD) is a derived, human-readable dump that can be regenerated from the HDF5 at any time.

`fd5` is **domain-agnostic by design**. The core format -- schema conventions, provenance DAG, units, hashing, metadata structure -- applies to any domain that produces immutable data products: medical imaging, detector physics, genomics, remote sensing, materials science, or machine-generated datasets from automated pipelines and AI systems. Domain-specific **product schemas** (which groups and datasets a particular product type requires) are layered on top of the core. This white paper defines the core conventions and provides the first set of product schemas from fd5's initial use case in medical imaging and nuclear physics.

`fd5` is format-agnostic on the input side. It does not parse DICOMs, ROOT files, FASTQ streams, or vendor-specific instrument output. Those are upstream concerns handled by domain-specific ingest pipelines. `fd5` defines what the clean, canonical data product looks like once it exists.


## Motivation

### The problem

Scientific data -- whether from medical imaging, particle detectors, sequencing instruments, automated lab equipment, or computational pipelines -- typically starts as vendor-specific output: DICOMs with thousands of inconsistent tags, proprietary binary formats, ad-hoc CSV/HDF5 layouts, and scattered metadata in spreadsheets, lab notebooks, and emails.

Working with this data involves:
- **Fragile caching layers** (JSON/pickle manifests that corrupt, go stale, or can't serialize domain types)
- **Repeated parsing overhead** (re-reading headers every time, re-computing derived quantities)
- **Scattered metadata** (acquisition parameters in one format, instrument settings in another, protocol details in a third, operator notes in emails)
- **No precomputed artifacts** (every visualization or summary requires loading full datasets)
- **No machine-readable schema** (new collaborators, AI agents, and automated pipelines must reverse-engineer the data structure)
- **No provenance chain** (which raw data produced this result? which calibration was applied? which pipeline version?)
- **Mutable state** (files modified in place, no integrity guarantee, no way to detect corruption or tampering)

These problems are universal. They appear wherever raw instrument output is transformed into analysis-ready data products -- in hospitals, synchrotrons, sequencing cores, simulation clusters, and AI training pipelines alike.

### The solution

Treat raw instrument output as archival source material -- keep it, hash it, link to it, but never work with it directly. Instead, ingest it once into a clean, self-describing, **immutable** format where:

1. One file = one data product (a reconstructed image, an event table, a processed spectrum, a variant call set)
2. All metadata lives inside the file, structured as nested groups with attributes
3. The schema is embedded in the file itself, not in external documentation
4. Precomputed artifacts (projections, thumbnails, summaries) are stored alongside the data
5. Provenance links trace every product back to its sources
6. The file is sealed with a content hash at write time and never modified
7. Any tool -- from `h5dump` to an LLM -- can understand the file without domain-specific code


## Design Principles

### 1. HDF5 is the single source of truth

The HDF5 file contains everything: data, metadata, schema, provenance, precomputed artifacts. All other representations are derived dumps. If the TOML manifest is deleted, regenerate it. If the datacite YAML is lost, regenerate it. The HDF5 file is canonical.

### 2. FAIR compliance (classic)

| Principle | Implementation |
|-----------|----------------|
| **Findable** | Persistent identifier (`id`) as root attribute. Rich, structured metadata. Human-readable filenames with timestamps. |
| **Accessible** | HDF5 is an open, standardized format supported by every scientific computing platform. No proprietary dependencies. |
| **Interoperable** | `@units` and `@unitSI` on every numerical field (NeXus/OpenPMD conventions). ISO 8601 timestamps with timezone. Standard vocabulary references via `_vocabulary`/`_code` attributes. |
| **Reusable** | Full provenance chain. Schema version embedded. `_type`/`_version` for forward-compatible extensibility. License and attribution metadata. |

### 3. AI-retrievable (FAIR for AI)

An AI agent encountering an `fd5` file should be able to:

- **Understand the structure** by reading the embedded `_schema` attribute (JSON Schema)
- **Understand the content** by reading `description` attributes on every group and dataset
- **Understand the units** by reading `@units` (human-readable) and `@unitSI` (numeric conversion factor)
- **Understand the vocabulary** by reading `*_vocabulary` attributes that map terms to standard codes
- **Understand the provenance** by following `sources/` group links
- **Understand the context** by reading study/subject/protocol metadata
- **Find the "interesting" data** by following the `default` attribute chain from root to the best dataset to visualize

No domain-specific code required. An `h5dump -A` (attributes only) produces a complete, self-documenting manifest of the file.

### 4. One file per data product

A single experiment, acquisition, or pipeline run may produce multiple data products with fundamentally different structures. Each gets its own file. This keeps files manageable, allows independent access, and matches the natural unit of scientific work ("I want the reconstruction" not "I want byte range 4.2--5.1 GB of the monolithic run file").

The concept of a "product type" is extensible. fd5 defines a core set of structural archetypes that cover common scientific data patterns:

| Structural archetype | Data structure | Examples across domains |
|---------------------|---------------|----------------------|
| N-dimensional array | Regular grid (3D, 4D, 5D) | Volumetric images, simulation fields, satellite rasters |
| Event table | Compound dataset, sequential rows | Detector events, sequencing reads, particle tracks |
| Projection / sinogram | AND array in transform coordinates | Projection data, Radon transforms, k-space |
| Histogram / spectrum | AND bins with axes and fit results | Energy spectra, lifetime distributions, expression matrices |
| Spatial transform | Matrix or displacement field | Image registrations, coordinate transforms |
| Calibration | Curves, maps, lookup tables | Gain maps, normalization tables, reference standards |
| Region of interest | Label masks, contours, geometric shapes | Segmentations, annotations, genomic intervals |
| Time series | Signal + time arrays | Device streams, sensor logs, physiological monitors |
| Simulation | Events + ground truth | Monte Carlo output, synthetic benchmarks |

Domain-specific **product schemas** map onto these archetypes. The first set of product schemas (defined later in this document) comes from medical imaging and nuclear physics: `recon`, `listmode`, `sinogram`, `spectrum`, `transform`, `calibration`, `roi`, `sim`, `device_data`. Other domains define their own product types using the same core conventions.

### 5. Groups are nested dicts

HDF5 groups with attributes provide native nested-dictionary storage. No JSON serialization, no custom encoders, no corruption from interrupted writes to text files. The helpers `h5_to_dict(group) -> dict` and `dict_to_h5(group, d)` provide round-trip conversion. Any HDF5 viewer can browse the structure.

### 6. `_type` + `_version` for forward-compatible extensibility

Any group that could have multiple implementations carries:
- `_type` (str): what kind of thing this is (e.g., `"q_clear"`, `"osem"`, `"bwa_mem2"`, `"random_forest"`)
- `_version` (int): which generation of that type's schema

A new algorithm, method, or pipeline step just uses a new `_type` value with its own attributes. **No schema change. No re-ingest of existing data.** Old readers encountering an unknown `_type` gracefully skip or display just the type string. `_version` handles breaking changes within a type; readers log warnings for unknown versions but still read what they can.

### 7. `@units` + `@unitSI` on every numerical field

Inspired by NeXus and OpenPMD:
- `units` (str): human-readable unit string (`"mm"`, `"s"`, `"MBq"`, `"keV"`)
- `unitSI` (float): numeric conversion factor to SI base units (`0.001` for mm, `1.0` for s, `1e6` for MBq)

Field names are bare (`z_min`, `duration`, `activity`) -- they do not embed units. This prevents the `z_min_mm` vs `z_min_m` vs `z_min_cm` naming chaos and enables automated unit conversion: `value_si = value * unitSI`.

**For attributes with physical units,** use a sub-group pattern that provides structural integrity:

```
z_min/
    attrs: {value: -450.2, units: "mm", unitSI: 0.001}
```

This ensures that deleting the group deletes everything (no orphaned `_units` attributes), enables programmatic enumeration (every sub-group with `value`+`units`+`unitSI` is a physical quantity), and eliminates suffix-stripping heuristics.

**For datasets with physical units,** follow the NeXus convention: `units` and `unitSI` are attributes on the dataset itself.

### 8. Additive-only schema evolution

New schema versions only add attributes and groups. They never remove or rename existing ones. A v2 reader can always read a v1 file. A v1 reader encountering v2 data reads what it knows and ignores the rest.

### 9. Embedded schema definition

The root of every `fd5` file carries a `_schema` attribute containing a JSON Schema document describing the file's structure. This is not for validation during normal use (though it can be) -- it's for **self-description**. An AI agent or unfamiliar tool reads `_schema` and knows exactly what groups and attributes to expect, their types, and their semantics.

**Storage rationale:**

The `_schema` is stored as a JSON string attribute (not as a group tree) for **single-read self-description**. One `h5py.File(f).attrs["_schema"]` call returns the complete schema without traversing the group tree. This is the fastest possible path for an AI agent or unfamiliar tool to understand the file structure.

- **Why not a group tree?** Storing the schema as a group tree (mirroring the actual data structure) would be redundant -- the actual data *is* the structural schema. Reconstructing the schema from a tree would require full traversal, defeating the purpose of fast introspection.

- **Why not binary format?** A binary-encoded format (MessagePack, CBOR, Protocol Buffers) could reduce size, but would sacrifice the property that `h5dump -A` produces human-readable output. The JSON `_schema` attribute is visible in any HDF5 viewer and in command-line dumps. For self-documentation, human readability trumps storage efficiency.

- **Read-optimized, write-once**: The JSON string is intentionally a read-optimized format. It's written once during file creation and read many times during discovery, validation, and AI-assisted analysis. The schema size (typically <10 KB) is negligible compared to data payloads (MB to GB).

### 10. ISO 8601 with explicit timezone

All timestamps include timezone offset: `"2024-07-24T18:14:00+02:00"`. No ambiguity when files move between institutions, time zones, or continents. Midnight in Vienna is not midnight in Boston.

### 11. Provenance as a DAG, not a string

A PET reconstruction depends on listmode data AND a CT for attenuation correction. A simulation reconstruction depends on simulated events AND a ground truth phantom definition. These relationships form a directed acyclic graph (DAG), stored in a `sources/` group with HDF5 external links to the source products. Each source also stores the source file's content hash for integrity verification.

Provenance lives in metadata, not in filenames. Filenames describe identity ("what is this"); metadata describes relationships ("where did it come from").

### 12. Two hashes, two purposes

Every `fd5` file carries two distinct hashes:

- **`id`** (root attr): SHA-256 of identity inputs (product-type-specific; e.g., `product + source + timestamp`), prefixed with algorithm: `"sha256:a1b2c3..."`. This is the **persistent identity** -- stable across re-ingests, schema upgrades, and recompression. The companion `id_inputs` attr documents exactly what was hashed. Filenames use the first 8 hex chars for brevity.
- **`content_hash`** (root attr): SHA-256 of the file's data content (excluding the hash attr itself), computed at write time: `"sha256:d4e5f6..."`. This is the **integrity seal** -- changes if anything in the file changes.

Additionally:
- `provenance/original_files`: compound dataset with `(path, sha256, size)` for every upstream source file
- `sources/*/content_hash`: SHA-256 of each referenced source product

This enables:
- **Stable identity**: re-ingesting the same data with a newer fd5 version keeps the same `id`
- **Integrity verification**: detect corruption or tampering via `content_hash`
- **Cache invalidation**: re-ingest only if source data changed
- **Reproducibility**: verify that the same inputs produce the same outputs

All hashes use the `"algorithm:hex"` prefix convention (currently always `"sha256:"`) so the algorithm is self-documenting and upgradeable.

### 13. Immutability and write-once semantics

fd5 files are **write-once, read-many (SWMR)**. Once a file is created and sealed with its `content_hash`, it is never modified. There is no `fd5.open_for_edit()`. This is a deliberate architectural choice, not a limitation:

- **Integrity**: the `content_hash` Merkle tree is valid for the lifetime of the file. No re-hashing after edits.
- **Provenance**: downstream products reference source products by `id` and `content_hash`. If a source file were modified, the entire provenance chain would be invalidated.
- **Concurrency**: multiple readers can access the file simultaneously without locks. HDF5's SWMR mode is supported natively.
- **Caching**: any cache keyed on `content_hash` is valid forever. No cache invalidation logic needed.
- **Reproducibility**: the same inputs to the same pipeline always produce files with the same `content_hash`.

If data needs to be corrected or reprocessed, the pipeline produces a **new** fd5 file with a new `id` and `content_hash`. The old file remains unchanged. Version history is tracked through the provenance DAG (`sources/`), not through in-place mutation.

This model is natural for data products generated by automated pipelines, AI inference systems, and instrument ingest processes -- all of which produce immutable outputs. It is the same model used by content-addressed storage systems (Git, IPFS, Zarr) and append-only databases.


## File Naming Convention

```
YYYY-MM-DD_HH-MM-SS_<product>-<id>_<descriptors>.h5
```

- **Datetime prefix**: creation/acquisition timestamp for chronological `ls` sorting
- **Product type**: domain-defined (e.g., `recon`, `listmode`, `spectrum`, `alignment`, `variants`, `features`)
- **ID**: first 8 hex chars of the full SHA-256 identity hash (for filename brevity)
- **Descriptors**: freeform, human-readable labels separated by underscores (domain, method, subset, etc.)

Examples (medical imaging):

```
2024-07-24_18-14-00_recon-87f032f6_ct_thorax_dlir.h5
2024-07-24_19-06-10_recon-2a3ac438_pet_qclear_wb.h5
2024-07-24_19-06-10_listmode-def67890_pet_coinc.h5
2024-07-24_19-30-00_spectrum-44556677_pet_lifetime_pals.h5
2024-07-24_19-06-10_roi-aabb1122_pet_tumor_contours.h5
sim-xyz99999_pet_nema_gate.h5
```

Examples (other domains):

```
2025-03-15_09-22-00_alignment-c4f2a1b8_wgs_sample01_bwamem2.h5
2025-03-15_10-45-00_variants-e7d3b902_wgs_sample01_deepvariant.h5
2025-06-01_12-00-00_features-a1b2c3d4_satellite_band4_ndvi.h5
2025-06-01_14-30-00_spectrum-f9e8d7c6_xrf_sample_cu_ka.h5
calibration-11223344_detector_energy_hpge.h5
```

Products without a natural timestamp (simulations, synthetic data, reference datasets) omit the datetime prefix.

The filename is **convenience, not identity**. The `<id>` in the filename is the first 8 hex characters of the full `id` hash (e.g., `sha256:2a3ac438e7f1...` becomes `2a3ac438` in the filename). The real identity is the full `id` attribute inside the HDF5 file. Renaming a file breaks nothing. The `fd5` package sets file `mtime` to the acquisition timestamp during creation, so file managers sort chronologically even without parsing the name.

Descriptors are freeform -- not BIDS-style `key-value` pairs. They exist for `ls` and `grep`, not for machine parsing. Machine-readable metadata lives inside the HDF5. Domains are free to establish naming conventions for their descriptors (e.g., `_wgs_` for whole-genome sequencing, `_pet_` for PET imaging) without changing the fd5 core.


## HDF5 Schema

### Root attributes (common to all products)

Every `fd5` file carries these attributes on the root group. The `study/` and `subject/` (or domain-equivalent context) groups provide self-containment:

| Attribute | Type | Description |
|-----------|------|-------------|
| `_schema` | str (JSON) | JSON Schema document describing this file's structure |
| `_schema_version` | int | fd5 schema version (monotonically increasing) |
| `product` | str | Product type: `"recon"`, `"listmode"`, `"sinogram"`, `"sim"`, `"transform"`, `"calibration"`, `"spectrum"`, `"roi"`, `"device_data"` |
| `id` | str | Persistent unique identifier, algorithm-prefixed SHA-256 of identity inputs (e.g., `"sha256:a1b2c3d4..."`) |
| `id_inputs` | str | Documents what was hashed to produce `id` (e.g., `"product + vendor + vendor_id + timestamp"`) |
| `name` | str | Human-readable name |
| `description` | str | Natural-language description of this data product |
| `domain` | str | Scientific domain (optional): `"medical_imaging"`, `"nuclear_physics"`, `"genomics"`, `"remote_sensing"`, etc. |
| `timestamp` | str | ISO 8601 with timezone |
| `content_hash` | str | Algorithm-prefixed SHA-256 of file content at write time (e.g., `"sha256:d4e5f6..."`) |
| `default` | str | Path to the "best" dataset for visualization |

Plus product-specific root attributes (see product schemas below).

### `description` attributes

**Every group and every dataset** in an `fd5` file carries a `description` attribute -- a short, natural-language string explaining what it is. This is the primary mechanism for AI-readability:

```
/metadata/reconstruction
    _type = "q_clear"
    _version = 1
    description = "Penalized-likelihood PET image reconstruction using GE Q.Clear algorithm"
    beta = 350
    iterations = 25
```

An `h5dump -A` of the file produces a complete human- and machine-readable manifest without any fd5-specific tooling.

**Description requirements:**
- **Required** on the root group and all first-level groups (`metadata/`, `provenance/`, `sources/`, etc.)
- **Recommended** on all deeper groups and datasets

**Quality enforcement:** The fd5 SDK integrates a lightweight validator at write time to reject boilerplate descriptions that merely restate the group name (e.g., `"Metadata"` for `metadata/`, `"Reconstruction parameters"` for `metadata/reconstruction/`). The validator can be a simple heuristic (string similarity check) or a small local LLM (e.g., quantized models via llama.cpp, mlx, or transformers) that scores description informativeness. This is an SDK concern, not a format concern -- the `description` attribute is always a plain string, and validation happens only during creation.

### Units convention

Every numerical attribute or dataset with physical meaning carries units information. The pattern differs for attributes vs. datasets:

**For attributes:** use a sub-group pattern where the physical quantity becomes a group with `value`, `units`, and `unitSI` attributes:

```
z_min/
    attrs: {value: -450.2, units: "mm", unitSI: 0.001}
duration/
    attrs: {value: 367.0, units: "s", unitSI: 1.0}
```

This provides structural integrity (delete the group, delete everything) and programmatic enumeration (every sub-group with these three attributes is a physical quantity).

**For datasets:** follow the NeXus convention where `units` and `unitSI` are attributes on the dataset itself:

```
volume                              # dataset: float32 (Z, Y, X)
    attrs: {units: "Bq/mL", unitSI: 1000.0, ...}
```

### Vocabulary references

Domain-specific string fields carry optional vocabulary attributes that link the human-readable value to a standard terminology:

```
# Medical imaging example:
scan_type = "pet"
scan_type_vocabulary = "DICOM Modality"
scan_type_code = "PT"

# Genomics example:
variant_type = "SNV"
variant_type_vocabulary = "Sequence Ontology"
variant_type_code = "SO:0001483"
```

These use **human-readable standard names** -- not hex tag IDs or obscure numeric codes. The vocabulary name itself is enough for lookup. Each domain uses its own standard vocabularies:
- **Medical imaging**: DICOM Modality (`CT`, `PT`, `MR`), SNOMED CT (anatomical regions), RadLex (procedures)
- **Genomics**: SO (Sequence Ontology), HGNC (gene names), OMIM (diseases)
- **Materials science**: CIF (crystallographic terms), MatOnto
- **General**: SI units, ISO standards

Vocabulary attributes are optional and additive. Their absence doesn't break anything. Domains are free to define additional vocabulary references without changing the fd5 core.

### `metadata/` group -- structured metadata

The `metadata/` group uses nested HDF5 groups to represent structured metadata as a dict-of-dicts. Each sub-group carries `_type` and `_version` for extensibility.

This replaces JSON/TOML/YAML metadata files. The structure is browsable in any HDF5 viewer, queryable via h5py, and round-trippable to Python dicts via `h5_to_dict()`.

Example for a PET reconstruction:

```
metadata/
    attrs: {_type: "pet", _version: 1,
            description: "PET acquisition and reconstruction metadata"}
    tracer/
        attrs: {name: "FDG",
                injection_time: "18:30:00+02:00",
                description: "Radiotracer administration details"}
        injection_activity/
            attrs: {value: 350.0, units: "MBq", unitSI: 1e6}
        half_life/
            attrs: {value: 6586.2, units: "s", unitSI: 1.0}
    acquisition/
        attrs: {n_beds: 4, mode: "3D",
                frame_durations: [120.0, 120.0, 120.0, 120.0],
                description: "Data acquisition parameters"}
        frame_durations/
            attrs: {value: [120.0, 120.0, 120.0, 120.0], units: "s", unitSI: 1.0}
    reconstruction/
        attrs: {_type: "q_clear", _version: 1,
                beta: 350, iterations: 25, tof: true, psf: true,
                description: "Penalized-likelihood reconstruction (GE Q.Clear)"}
        references/                                 # optional: NXcite pattern
            method_paper/
                attrs: {doi: "10.1088/0031-9155/60/10/3777",
                        description: "Original Q.Clear penalized-likelihood algorithm paper"}
            validation/
                attrs: {doi: "10.2967/jnumed.117.200071",
                        description: "Clinical validation of Q.Clear vs OSEM"}
    corrections/
        attenuation/
            attrs: {_type: "ct_based", _version: 1,
                    description: "CT-based attenuation correction"}
        scatter/
            attrs: {_type: "model_based", _version: 1,
                    scatter_fraction: 0.35,
                    description: "Model-based scatter correction"}
```

Example for a CT reconstruction:

```
metadata/
    attrs: {_type: "ct", _version: 1}
    acquisition/
        attrs: {pitch: 0.984,
                description: "CT acquisition parameters"}
        kvp/
            attrs: {value: 120, units: "kV", unitSI: 1000.0}
        mas/
            attrs: {value: 250, units: "mAs", unitSI: 1.0}
        rotation_time/
            attrs: {value: 0.5, units: "s", unitSI: 1.0}
    reconstruction/
        attrs: {_type: "dlir", _version: 1,
                strength: "medium", kernel: "STANDARD",
                description: "Deep learning image reconstruction"}
    dose/
        ctdi_vol/
            attrs: {value: 12.5, units: "mGy", unitSI: 0.001}
        dlp/
            attrs: {value: 450.0, units: "mGy*cm", unitSI: 0.01}
```

New metadata sub-groups (e.g., `contrast/`, `respiratory_gating/`, `cardiac_gating/`) are added as needed. Unknown groups are ignored by readers that don't understand them.

### `sources/` group -- provenance DAG

Each named sub-group represents one input to this data product:

```
sources/
    description = "Data products this file was derived from"
    emission/
        attrs: {id: "sha256:def67890...",
                product: "listmode",
                file: "2024-07-24_19-06-10_listmode-def67890_pet_coinc.h5",
                content_hash: "sha256:a1b2c3...",
                role: "emission_data",
                description: "PET listmode coincidence data used for reconstruction"}
        --> h5py.ExternalLink("../2024-07-24_19-06-10_listmode-def67890_pet_coinc.h5", "/")
    attenuation/
        attrs: {id: "sha256:21d255e7...",
                product: "recon",
                file: "2024-07-24_18-25-00_recon-21d255e7_ct_ctac.h5",
                content_hash: "sha256:d4e5f6...",
                role: "mu_map",
                description: "CT reconstruction used for attenuation correction (mu-map)"}
        --> h5py.ExternalLink("../2024-07-24_18-25-00_recon-21d255e7_ct_ctac.h5", "/")
```

**Resolution semantics:**

- The **`id` hash is the primary resolution key**, not the relative file path. The `file` attribute is a convenience hint that may become stale if files are moved or reorganized.
- The external link provides transparent HDF5 access to source data *when the file is at the hinted location*. If the link is broken (file moved), resolution falls back to the `id`.
- The `content_hash` enables integrity verification after resolution, decoupling "find the file" from "verify the file."

**File location management is out of scope** for the fd5 format. It is the responsibility of dataset management tools:
- **DataLad**: version-controlled datasets with content-addressable storage
- **Local metadata table**: Polars/DuckDB table mapping `id` → `path` for the current dataset
- **Vector DB**: LanceDB or similar for fast hash-based lookup across large collections

**Resolution layer:** The fd5 SDK provides a `resolve(id) -> Path` hook that dataset managers can implement. The default implementation:
1. Check if the external link works (file exists at hinted path)
2. If not, search the manifest (`manifest.toml`) for a product with matching `id`
3. If not found, raise `SourceNotFoundError` with the `id` for the user to handle

External tools (DataLad, custom registries) can override this hook to provide richer resolution (e.g., automatic git-annex retrieval, remote registry queries).

Source groups can themselves be queried recursively to reconstruct the full provenance tree.

### `provenance/` group -- original file provenance

```
provenance/
    description = "Provenance of the original source files ingested into this product"
    original_files    # compound dataset: (path: str, sha256: str, size_bytes: int)
    ingest/
        attrs: {tool: "duplet_ingest",
                tool_version: "0.3.1",
                timestamp: "2026-02-11T15:00:00+01:00",
                description: "Ingest pipeline that created this file"}
```

### `extra/` group -- unvalidated collection

Inspired by NeXus `NXcollection`. A catch-all for vendor-specific data, experimental annotations, operator notes, or anything outside the schema. Explicitly excluded from validation.

```
extra/
    description = "Unvalidated, vendor-specific, or experimental metadata"
    ge_specific/
        attrs: {recon_software: "PetRecon 4.2.1",
                description: "GE-specific reconstruction software metadata"}
    notes/                                          # optional: NXnote pattern for binary attachments
        operator_screenshot/
            attrs: {author: "Dr. Smith",
                    date: "2024-07-24T19:30:00+02:00",
                    type: "image/png",              # MIME type
                    description: "Screenshot of scanner console showing motion artifact"}
            data                    # dataset: binary (opaque bytes)
        protocol_pdf/
            attrs: {author: "Lab Manager",
                    date: "2024-07-24",
                    type: "application/pdf",
                    file_name: "DOGPLET_protocol_v3.pdf",
                    description: "Scan protocol document"}
            data                    # dataset: binary
```

The `notes/` sub-group follows the NeXus NXnote pattern for attaching freeform binary content (photos, PDFs, screenshots) with MIME typing. Optional, never required. Each attachment has a `data` dataset containing the binary payload and metadata attributes including MIME type, authorship, and description.

**Size guidelines and preference hierarchy:**

The capability to embed binary attachments exists for cases where a blob is truly inseparable from the data product. However, **metadata catalogs (RO-Crate, DataLad, institutional repositories) are the preferred mechanism** for associating supplementary materials.

| Size | Recommendation |
|------|---------------|
| **< 1 MB** | Embed freely (screenshots, small config files, operator notes) |
| **1-10 MB** | Embed **only if** the content is inseparable from this specific data product (e.g., a scanner console screenshot showing a specific artifact visible in this acquisition) |
| **> 10 MB** | **Strongly prefer external references** via RO-Crate, DataLad, DOI, or institutional repository. Store a reference (URL, DOI, hash) in `extra/notes/` instead of the binary payload |

**Example external reference:**

```
extra/
    notes/
        protocol_reference/
            attrs: {type: "application/pdf",
                    url: "https://doi.org/10.5281/zenodo.1234567",
                    file_name: "DOGPLET_protocol_v3.pdf",
                    sha256: "abc123...",
                    description: "Scan protocol document (externally hosted)"}
```

Embedding large binaries violates the "one product, manageable size" principle and makes files harder to transfer, archive, and process.

### Reserved conventions

| Convention | Meaning | Status |
|------------|---------|--------|
| `_type` | Polymorphic type identifier on a group | Active |
| `_version` | Schema version for a `_type` | Active |
| `_schema` | Embedded JSON Schema (root only) | Active |
| `_schema_version` | fd5 format version (root only) | Active |
| `_errors` | Uncertainty dataset with same shape as parent | Active (used in `spectrum/counts_errors`) |
| `_vocabulary` | Vocabulary system name suffix | Active |
| `_code` | Standard code suffix in named vocabulary | Active |
| `description` | Natural-language description on any group/dataset | Active |
| `default` | Path to recommended visualization target | Active |
| `id` | Algorithm-prefixed SHA-256 of identity inputs (root only) | Active |
| `id_inputs` | Documents what was hashed to produce `id` (root only) | Active |
| `content_hash` | Algorithm-prefixed SHA-256 of file content at write time | Active |

**Units convention:** Physical quantities stored as attributes use a sub-group pattern: `<name>/` with `attrs: {value, units, unitSI}`. Physical quantities stored as datasets carry `units` and `unitSI` as attributes on the dataset (NeXus convention).


### `study/` group -- study context and FAIR metadata

Study-level metadata describing the research context, funding, and legal framework. This group is **domain-agnostic** and appears in every data product file (inherited or repeated for convenience).

```
study/
    attrs: {type: str,                               # domain-defined: "clinical", "research", "calibration", "synthetic", etc.
            license: "CC-BY-4.0",                    # SPDX identifier or URL (RO-Crate required)
            license_url: "https://creativecommons.org/licenses/by/4.0/",  # optional
            description: "Study type and context"}
    creators/                                        # optional: RO-Crate author field
        creator_0/
            attrs: {name: "Jane Doe",
                    affiliation: "ETH Zurich",
                    orcid: "https://orcid.org/0000-0002-1234-5678",  # optional
                    role: "principal_investigator",                    # optional: pi, data_collection, analysis
                    description: "Study creator"}
        creator_1/
            attrs: {name: "John Smith",
                    affiliation: "University Hospital Zurich",
                    role: "data_collection",
                    description: "Study creator"}
```

**FAIR compliance:** The `license` and `creators/` fields are required for RO-Crate export. `license` must be an SPDX identifier (e.g., `"CC-BY-4.0"`, `"CC0-1.0"`) or URL. `creators/` enables Schema.org `Person` entity mapping with affiliation and ORCID support.

### Context groups -- domain-specific metadata

Beyond `study/`, each domain defines context groups relevant to its data. These are optional at the fd5 core level but may be required by a domain schema. Examples:

**Medical imaging** (`subject/`, `phantom/`):

```
subject/
    attrs: {id: "anonymized_id" | "patient_12345",
            species: "human" | "dog" | "mouse" | "phantom",
            sex: "M" | "F" | "other",                # optional
            birth_date: "1959-03-15",                # optional (privacy-sensitive)
            description: "Subject demographics"}
    age/                                             # optional for human subjects (privacy)
        attrs: {value: 42.5, units: "years", unitSI: 31557600.0}
    weight/                                          # optional
        attrs: {value: 75.0, units: "kg", unitSI: 1.0}
```

**Genomics** (`sample/`, `library/`):

```
sample/
    attrs: {sample_id: "TCGA-AB-1234",
            organism: "Homo sapiens",
            tissue: "liver",
            tissue_vocabulary: "UBERON",
            tissue_code: "UBERON:0002107",
            description: "Biological sample metadata"}
```

**Privacy:** For all domains, sensitive fields (birth dates, patient IDs, GPS coordinates) should be omitted or generalized in de-identified datasets. The fd5 core does not enforce privacy policy -- that is the responsibility of the domain schema and the ingest pipeline.

## Product Schemas

The product schemas below define the required and optional groups and datasets for each product type. They are **the first set of schemas**, developed for fd5's initial use case in medical imaging and nuclear/positron physics.

New domains add new product schemas by following the same conventions: root attributes, `metadata/` group with `_type`/`_version`, `sources/` provenance DAG, `provenance/` original file tracking, and `extra/` for unvalidated data. The core fd5 machinery (hashing, schema embedding, manifest generation, RO-Crate export) works identically regardless of the product type.

**Defining new product schemas** requires only:
1. Choose a `product` string (e.g., `"alignment"`, `"expression_matrix"`, `"feature_set"`)
2. Define required datasets and their structure (compound tables, AND arrays, etc.)
3. Define required `metadata/` sub-groups with `_type`/`_version`
4. Define `id_inputs` for identity hashing
5. Register the schema as a JSON Schema document

No changes to the fd5 core library are needed.

---

### `recon` -- Reconstruction

A 3D, 4D, or 5D image volume with a multiscale resolution pyramid and precomputed projections. Covers static images, dynamic (multi-frame) time series, gated (cardiac/respiratory) reconstructions, parametric maps, dose maps, and attenuation maps.

The volume dimensionality depends on the reconstruction:

| Case | Shape | Dimension semantics |
|------|-------|-------------------|
| Static (CT, static PET, MRI) | `(Z, Y, X)` | Spatial only |
| Dynamic PET (time frames) | `(T, Z, Y, X)` | Time x spatial |
| Gated (cardiac/respiratory) | `(G, Z, Y, X)` | Gate bin x spatial |
| Dynamic + gated | `(G, T, Z, Y, X)` | Gate x time x spatial |
| Multi-energy CT | `(E, Z, Y, X)` | Energy bin x spatial |

```
<file>.h5
├── attrs: (common) + {n_slices}
├── z_min/
│   attrs: {value: -850.0, units: "mm", unitSI: 0.001}
├── z_max/
│   attrs: {value: -12.5, units: "mm", unitSI: 0.001}
├── duration/
│   attrs: {value: 367.0, units: "s", unitSI: 1.0}
│
├── metadata/                       # structured acquisition + reconstruction params
│   # (see detailed PET/CT metadata examples in the metadata section above)
│
├── volume                          # dataset: float32, shape depends on dimensionality
│   attrs: {
│       affine: float64[4,4],       # spatial affine (always 3D: maps voxel to mm)
│       reference_frame: str,
│       dimension_order: str,       # e.g. "TZYX", "GZYX", "GTZYX", "ZYX"
│       description: str
│   }
│
├── frames/                         # REQUIRED for 4D+ data; absent for static 3D
│   attrs: {
│       n_frames: int,
│       frame_type: str,            # "time" | "gate_cardiac" | "gate_respiratory" | "energy"
│       description: str
│   }
│   frame_start                     # dataset: float64 (N_frames,) -- frame start times
│       attrs: {units: "s", unitSI: 1.0,
│               reference: str,     # "injection" | "scan_start" | "midnight"
│               description: "Start time of each frame relative to reference"}
│   frame_duration                  # dataset: float64 (N_frames,) -- per-frame durations
│       attrs: {units: "s", unitSI: 1.0,
│               description: "Duration of each frame (non-uniform allowed)"}
│   frame_label                     # dataset: variable-length string (N_frames,) -- optional
│       attrs: {description: "Human-readable label per frame, e.g. 'systole', 'diastole'"}
│   │
│   │   # --- for gated data ---
│   gate_phase                      # dataset: float64 (N_gates,) -- phase within cycle
│       attrs: {units: "%",         # 0-100% of cardiac/respiratory cycle
│               description: "Phase within physiological cycle per gate bin"}
│   gate_trigger/                   # optional: the raw gating signal
│       signal                      # dataset: float64 (N_samples,) -- raw ECG/bellows/etc.
│           attrs: {description: "Raw physiological gating signal"}
│       sampling_rate/
│           attrs: {value: 500.0, units: "Hz", unitSI: 1.0}
│       trigger_times               # dataset: float64 (N_triggers,)
│           attrs: {units: "s", unitSI: 1.0, description: "Detected trigger timestamps"}
│
├── pyramid/                        # multiscale resolution pyramid (inspired by SOME-Zarr NGFF)
│   attrs: {
│       n_levels: int,              # number of downsampled levels (excluding full-res volume)
│       scale_factors: list[int],   # e.g. [2, 4, 8] -- each relative to full-res volume
│       method: str,                # "local_mean" | "stride" | "gaussian" | "area"
│       description: "Multiscale pyramid for progressive-resolution access"
│   }
│   level_1/                        # 2x downsampled
│       volume                      # dataset: same dtype as root volume, shape / 2
│           attrs: {
│               affine: float64[4,4],
│               scale_factor: 2,
│               description: "2x downsampled volume"
│           }
│   level_2/                        # 4x downsampled
│       volume                      # dataset: shape / 4
│           attrs: {scale_factor: 4, ...}
│   level_3/                        # 8x downsampled (thumbnail-scale)
│       volume                      # dataset: shape / 8
│           attrs: {scale_factor: 8, ...}
│
├── mip_coronal                     # float32, (Z, X) -- MIP of summed/static volume
│   attrs: {projection_type: "mip", axis: 1,
│           description: "Coronal MIP (summed over all frames if dynamic)"}
├── mip_sagittal                    # float32, (Z, Y)
│   attrs: {projection_type: "mip", axis: 2,
│           description: "Sagittal MIP (summed over all frames if dynamic)"}
│
├── mips_per_frame/                 # optional: per-frame MIPs for dynamic data
│   coronal                         # float32, (T, Z, X) -- one MIP per frame
│       attrs: {projection_type: "mip", axis: 1, description: "Per-frame coronal MIPs"}
│   sagittal                        # float32, (T, Z, Y)
│       attrs: {projection_type: "mip", axis: 2, description: "Per-frame sagittal MIPs"}
│
├── device_data/                       # optional: embedded device streams (NXlog pattern)
│   attrs: {description: "Device signals recorded during this acquisition"}
│   ecg/
│       attrs: {_type: "ecg", _version: 1,
│               model: "GE CardioLab",
│               measurement: "voltage",
│               run_control: true,
│               description: "ECG trace for cardiac gating"}
│       sampling_rate/
│           attrs: {value: 500, units: "Hz", unitSI: 1.0}
│       signal              # dataset: float64 (N,)
│           attrs: {units: "mV", unitSI: 0.001}
│       time                # dataset: float64 (N,)
│           attrs: {units: "s", unitSI: 1.0, start: "2024-07-24T19:06:10+02:00"}
│       average_value, minimum_value, maximum_value, duration (optional summary stats)
│       cue_timestamp_zero  # optional: coarse timestamps (e.g. every 60s)
│       cue_index           # optional: index into time/signal at each cue
│
├── sources/                        # provenance DAG
├── provenance/
│   original_files                  # compound dataset: (path, sha256, size_bytes)
│   dicom_header                    # variable-length string (JSON via pydicom.Dataset.to_json())
│   │   attrs: {description: "Full DICOM header from representative source file, round-trippable"}
│   │                               # OPTIONAL: only present when ingested from DICOM
│   per_slice_metadata              # compound dataset (instance_number, slice_location,
│   │                               #   acquisition_time, image_position_patient)
│   │                               # OPTIONAL: only present when ingested from DICOM
│   ingest/
│       attrs: {tool, tool_version, timestamp, description}
├── study/                          # study context (see Implementation Notes)
├── subject/                        # subject demographics (see Implementation Notes)
└── extra/                          # unvalidated vendor data
```

**Chunking strategy:**

| Dimensionality | Chunk shape | Rationale |
|---------------|------------|-----------|
| 3D `(Z,Y,X)` | `(1, Y, X)` | Efficient single-slice reads |
| 4D `(T,Z,Y,X)` | `(1, 1, Y, X)` | Efficient single-frame single-slice reads |
| 5D `(G,T,Z,Y,X)` | `(1, 1, 1, Y, X)` | Same pattern, one leading dim at a time |

Compression: gzip level 4 throughout.

**Multiscale pyramid** (inspired by SOME-Zarr NGFF):

The `pyramid/` group stores successively downsampled copies of the full-resolution `volume`, enabling progressive-resolution access without loading the entire dataset. This is the same core idea behind SOME-Zarr's multiscale image pyramids, adapted to HDF5's single-file model.

Each pyramid level halves the spatial dimensions relative to the previous level. The `scale_factors` root attribute lists the factor relative to the full-resolution volume (e.g., `[2, 4, 8]`). The downsampling `method` attribute records how the levels were computed (e.g., `"local_mean"` for anti-aliased averaging, `"stride"` for simple subsampling). Each level carries its own `affine` matrix reflecting the coarser voxel spacing.

| Level | Typical shape (for 512x512x300 volume) | Typical size | Use case |
|-------|----------------------------------------|-------------|----------|
| Full-res (`volume`) | `(300, 512, 512)` | 300 MB | Full analysis, ROI statistics |
| `level_1` (2x) | `(150, 256, 256)` | 37 MB | Interactive slice browsing |
| `level_2` (4x) | `(75, 128, 128)` | 4.7 MB | Quick 3D overview |
| `level_3` (8x) | `(38, 64, 64)` | 600 KB | Thumbnail, dataset gallery |

Pyramid levels are **derived artifacts** -- they can always be regenerated from the full-resolution volume. They are optional but strongly recommended for `recon` products. For dynamic (4D+) data, pyramid levels are computed per-frame or on the summed volume, depending on the use case; the `dimension_order` attribute on each level's volume clarifies the layout.

Pyramid chunking follows the same slice-based strategy as the full-resolution volume: `(1, Y_level, X_level)` for 3D levels. Lower levels are small enough that a single chunk per slice is efficient.

**Dynamic PET specifics:**

Frame durations in dynamic PET are typically non-uniform (e.g., 6x10s, 6x30s, 6x60s, 6x300s for a 44-minute scan). The `frames/frame_duration` dataset stores the actual duration per frame -- no assumption of uniformity. The `frames/frame_start` dataset stores absolute start times relative to a stated reference (usually tracer injection).

**Gated specifics:**

For cardiac gating, the `frame_type` is `"gate_cardiac"` and `gate_phase` records the percentage within the R-R interval (0% = end-diastole, ~35% = end-systole). For respiratory gating, `frame_type` is `"gate_respiratory"`. The raw gating signal (ECG trace, bellows signal) can optionally be stored in `frames/gate_trigger/` for quality assessment.

**Parametric maps (pmap):**

Parametric maps (K_i, V_d, ADC, T1/T2, SUV) are stored as `recon` products. They are 3D volumes with the same spatial structure. Their `metadata/reconstruction/_type` identifies them (e.g., `_type: "patlak"`, `_type: "logan"`, `_type: "adc"`) and carries model-specific parameters. Their `sources/` link back to the dynamic `recon` and any input functions used for kinetic modeling.

### `listmode` -- Event-based Data

Detector-level event streams (singles, coincidences, time markers).

```
<file>.h5
├── attrs: (common) + {mode, table_pos, duration, z_min, z_max}
│
├── metadata/
│   daq/                            # data acquisition system parameters (from INI/config)
│       attrs: {acq_mode, gain_cal, energy_cal, ...}
│
├── raw_data/                       # raw detector events
│   singles       (N,) compound
│   time_markers  (N,) compound
│   coin_counters (N,) compound
│   table_positions (N,) compound
│
├── proc_data/                      # processed events (if available)
│   events_2p     (N,) compound
│   events_3p     (N,) compound
│   coin_2p       (N,) compound
│   coin_3p       (N,) compound
│
├── device_data/                       # optional: embedded device streams (NXlog pattern)
│   attrs: {description: "Device signals recorded during this acquisition"}
│   ecg/
│       attrs: {_type: "ecg", _version: 1,
│               model: "GE CardioLab",
│               measurement: "voltage",
│               run_control: true,
│               description: "ECG trace for cardiac gating"}
│       sampling_rate/
│           attrs: {value: 500, units: "Hz", unitSI: 1.0}
│       signal              # dataset: float64 (N,)
│           attrs: {units: "mV", unitSI: 0.001}
│       time                # dataset: float64 (N,)
│           attrs: {units: "s", unitSI: 1.0, start: "2024-07-24T19:06:10+02:00"}
│       average_value, minimum_value, maximum_value, duration (optional summary stats)
│       cue_timestamp_zero  # optional: coarse timestamps (e.g. every 60s)
│       cue_index           # optional: index into time/signal at each cue
│
├── sources/
├── provenance/
└── extra/
```

### `sinogram` -- Projection Data

Projection-space data (sinograms, michelogram, raw projections) before image reconstruction. Structurally a 3D or 4D array indexed by detector coordinates (radial, angular, axial ring-difference, optionally TOF bin), not by spatial coordinates.

```
<file>.h5
├── attrs: (common)
│   product: "sinogram"
│   n_radial: int
│   n_angular: int
│   n_planes: int
│   span: int                           # axial compression factor
│   max_ring_diff: int
│   tof_bins: int                       # 0 or 1 = non-TOF
│
├── metadata/
│   acquisition/
│       attrs: {n_rings: int, n_crystals_per_ring: int,
│               description: "Scanner geometry"}
│       ring_spacing/
│           attrs: {value: float, units: "mm", unitSI: 0.001}
│       crystal_pitch/
│           attrs: {value: float, units: "mm", unitSI: 0.001}
│   corrections_applied/
│       attrs: {normalization: bool, attenuation: bool, scatter: bool,
│               randoms: bool, dead_time: bool, decay: bool,
│               description: "Which corrections have been applied to this sinogram"}
│
├── sinogram                            # dataset: float32 (n_planes, n_angular, n_radial)
│   attrs: {description: "Projection data in sinogram format"}
│                                       # 4D with TOF: (n_planes, n_tof, n_angular, n_radial)
│
├── additive_correction                 # dataset: same shape -- scatter + randoms estimate
│   attrs: {description: "Additive correction term (scatter + randoms)"}
│
├── multiplicative_correction           # dataset: same shape -- norm * atten
│   attrs: {description: "Multiplicative correction term (normalization * attenuation)"}
│
├── sources/
├── provenance/
└── extra/
```


### `sim` -- Simulation

Simulated data with ground truth.

```
<file>.h5
├── attrs: (common, no timestamp prefix)
│
├── metadata/
│   simulation/
│       attrs: {_type: "gate", _version: 1,
│               gate_version, physics_list, n_primaries, random_seed, ...}
│       geometry/
│           attrs: {phantom, ...}
│       source/
│           attrs: {activity_distribution, activities, ...}
│
├── events/                         # simulated detector events (same structure as listmode)
│   events_2p     (N,) compound
│   events_3p     (N,) compound
│
├── ground_truth/                   # known true distributions (unique to simulation)
│   activity      (Z,Y,X) float32
│   attenuation   (Z,Y,X) float32
│
├── sources/                        # links to input phantoms, configs, etc.
├── provenance/
└── extra/
```


### `transform` -- Spatial Registrations

The result of co-registering two images: a spatial transformation that maps coordinates from one image space to another. Transforms are first-class data products because many downstream operations depend on them (resampled images, propagated ROIs, motion-corrected frames), and their provenance (which images, which algorithm, what quality) must be tracked.

```
<file>.h5
├── attrs: (common)
│   product: "transform"
│   transform_type: str                 # "rigid", "affine", "deformable", "bspline"
│   direction: str                      # "source_to_target" or "target_to_source"
│   default: "matrix" | "displacement_field"
│
├── metadata/
│   method/
│   │   attrs: {_type: "rigid" | "affine" | "deformable" | "bspline" | "manual_landmark",
│   │           _version: 1,
│   │           description: "..."}
│   │
│   │   # --- _type: "rigid" ---
│   │   attrs: {optimizer: "gradient_descent", metric: "mutual_information",
│   │           n_iterations: 200, convergence: 1e-6}
│   │
│   │   # --- _type: "deformable" ---
│   │   attrs: {optimizer: "LBFGS", metric: "cross_correlation",
│   │           regularization: "bending_energy", regularization_weight: 1.0,
│   │           n_levels: 3}
│   │   grid_spacing/
│   │       attrs: {value: [4.0, 4.0, 4.0], units: "mm", unitSI: 0.001}
│   │
│   │   # --- _type: "manual_landmark" ---
│   │   attrs: {n_landmarks: 12, operator: "Dr. Smith"}
│   │
│   quality/
│       attrs: {metric_value: float,    # final metric value
│               jacobian_min: float,    # minimum Jacobian determinant (deformable only)
│               jacobian_max: float,    # negative = folding
│               description: "Registration quality metrics"}
│       tre/                            # target registration error (if landmarks available)
│           attrs: {value: float, units: "mm", unitSI: 0.001}
│
├── matrix                              # dataset: float64 (4, 4) -- for rigid/affine
│   attrs: {description: "4x4 affine transformation matrix (homogeneous coordinates)",
│           convention: "LPS" | "RAS",
│           units: "mm"}
│
├── displacement_field                  # dataset: float32 (Z, Y, X, 3) -- for deformable
│   attrs: {affine: float64[4,4],       # defines the grid in physical space
│           reference_frame: str,
│           component_order: ["z", "y", "x"],  # or ["x", "y", "z"]
│           description: "Dense displacement vector field in mm"}
│
├── inverse_matrix                      # dataset: float64 (4, 4) -- optional, for rigid/affine
│   attrs: {description: "Inverse transformation matrix"}
│
├── inverse_displacement_field          # dataset: float32 (Z, Y, X, 3) -- optional
│   attrs: {description: "Inverse displacement field (approximate for deformable)"}
│
├── landmarks/                          # optional: corresponding point pairs
│   source_points                       # dataset: float64 (N, 3)
│       attrs: {units: "mm", description: "Landmark positions in source image space"}
│   target_points                       # dataset: float64 (N, 3)
│       attrs: {units: "mm", description: "Landmark positions in target image space"}
│   labels                              # dataset: variable-length string (N,)
│       attrs: {description: "Anatomical labels for each landmark pair"}
│
├── sources/
│   source_image/
│       attrs: {id, product: "recon", role: "source_image",
│               description: "Image being transformed (moving image)"}
│       --> h5py.ExternalLink(...)
│   target_image/
│       attrs: {id, product: "recon", role: "target_image",
│               description: "Reference image (fixed image)"}
│       --> h5py.ExternalLink(...)
│
├── provenance/
└── extra/
```

**Transform types:**

| `transform_type` | Data | Typical use |
|-------------------|------|-------------|
| `rigid` | 4x4 matrix (6 DOF: 3 rotation + 3 translation) | PET-to-CT alignment, follow-up registration |
| `affine` | 4x4 matrix (12 DOF) | Cross-modality, different FOV |
| `deformable` | Dense displacement field `(Z,Y,X,3)` | Anatomical atlas mapping, motion correction |
| `bspline` | Control point grid + knot vectors | Compact deformable representation |

The `direction` attribute is critical: it states whether the transform maps source-to-target or target-to-source coordinates. Ambiguity here is a common source of bugs.

Both forward and inverse transforms can be stored in the same file when available (`matrix` + `inverse_matrix`, or `displacement_field` + `inverse_displacement_field`).


### `calibration` -- Detector / Scanner Calibration

Calibration data that other products depend on: gain maps, energy calibration curves, normalization tables, dead-time coefficients, crystal efficiency maps, timing calibrations. These are scanner-specific, time-stamped, and referenced by downstream products via `sources/`.

Calibration products are structurally diverse (1D curves, 2D maps, lookup tables, matrices), so the schema is intentionally flexible -- the `_type`/`_version` on `metadata/calibration/` determines what datasets are expected.

```
<file>.h5
├── attrs: (common)
│   product: "calibration"
│   calibration_type: str               # high-level category (see table below)
│   scanner_model: str                  # e.g. "GE Discovery MI"
│   scanner_serial: str                 # specific scanner instance
│   valid_from: str                     # ISO 8601 -- start of validity window
│   valid_until: str                    # ISO 8601 -- end of validity (or "indefinite")
│   default: str                        # path to primary calibration dataset
│
├── metadata/
│   calibration/
│   │   attrs: {_type: "energy_calibration" | "gain_map" | "normalization"
│   │                   | "dead_time" | "timing_calibration" | "crystal_map"
│   │                   | "sensitivity" | "cross_calibration",
│   │           _version: 1,
│   │           description: "..."}
│   │
│   │   # --- _type: "energy_calibration" ---
│   │   attrs: {n_channels: 1024, fit_model: "linear",
│   │           coefficients: [0.0, 1.47],  # channel -> keV
│   │           coefficients_labels: ["offset", "gain"],
│   │           reference_sources: ["22Na", "137Cs"]}
│   │
│   │   # --- _type: "normalization" ---
│   │   attrs: {method: "component_based",
│   │           n_crystals_axial: 36, n_crystals_transaxial: 672}
│   │   acquisition_duration/
│   │       attrs: {value: 14400.0, units: "s", unitSI: 1.0}
│   │
│   │   # --- _type: "cross_calibration" ---
│   │   attrs: {reference_instrument: "dose_calibrator",
│   │           reference_model: "Capintec CRC-55tR",
│   │           calibration_factor: 1.023, calibration_factor_error: 0.008,
│   │           phantom: "uniform_cylinder"}
│   │   activity/
│   │       attrs: {value: 45.0, units: "MBq", unitSI: 1e6}
│   │
│   conditions/
│       temperature/
│           attrs: {value: 22.0, units: "degC", unitSI: 1.0}
│       humidity/
│           attrs: {value: 45.0, units: "%", unitSI: 0.01}
│       attrs: {description: "Environmental conditions during calibration"}
│
├── data/                               # calibration datasets -- structure depends on _type
│   │
│   │   # --- energy_calibration ---
│   │   channel_to_energy               # dataset: float64 (N_channels,) -- lookup table
│   │       attrs: {units: "keV", description: "Energy per channel"}
│   │   reference_spectrum              # dataset: float64 (N_channels,) -- calibration spectrum
│   │       attrs: {description: "Measured spectrum of calibration source"}
│   │
│   │   # --- gain_map ---
│   │   gain_map                        # dataset: float32 (N_axial, N_transaxial)
│   │       attrs: {description: "Per-crystal gain correction factors"}
│   │
│   │   # --- normalization ---
│   │   norm_factors                    # dataset: float32 -- shape depends on scanner geometry
│   │       attrs: {description: "Normalization correction factors"}
│   │   efficiency_map                  # dataset: float32 (N_axial, N_transaxial)
│   │       attrs: {description: "Per-crystal detection efficiency"}
│   │
│   │   # --- dead_time ---
│   │   dead_time_curve                 # dataset: float64 (N_points, 2) -- (count_rate, correction_factor)
│   │       attrs: {count_rate__units: "cps",
│   │               description: "Dead-time correction as function of count rate"}
│   │
│   │   # --- timing_calibration ---
│   │   timing_offsets                  # dataset: float32 (N_crystals,) or (N_axial, N_transaxial)
│   │       attrs: {units: "ns", description: "Per-crystal timing offset corrections"}
│   │   resolution_curve                # dataset: float64 (N_points, 2) -- (energy, fwhm)
│   │       attrs: {energy__units: "keV", fwhm__units: "ns",
│   │               description: "Timing resolution as function of energy"}
│
├── sources/                            # what was used to produce this calibration
│   calibration_data/
│       attrs: {id, product: "listmode", role: "calibration_acquisition", ...}
│       --> h5py.ExternalLink(...)
│
├── provenance/
└── extra/
```

**Calibration types:**

| `calibration_type` | What it calibrates | Key datasets |
|--------------------|-------------------|--------------|
| `energy_calibration` | Channel-to-energy mapping | `channel_to_energy`, `reference_spectrum` |
| `gain_map` | Per-crystal gain correction | `gain_map` |
| `normalization` | Detector efficiency normalization | `norm_factors`, `efficiency_map` |
| `dead_time` | Count-rate-dependent dead-time | `dead_time_curve` |
| `timing_calibration` | Per-crystal timing offsets, TOF resolution | `timing_offsets`, `resolution_curve` |
| `crystal_map` | Crystal-to-position mapping | `crystal_positions`, `crystal_ids` |
| `sensitivity` | System sensitivity (cps/MBq) | `sensitivity_profile` |
| `cross_calibration` | Scanner-to-dose-calibrator factor | Stored in metadata attrs |

**Validity window:** The `valid_from` / `valid_until` timestamps define when this calibration is applicable. Downstream products reference a specific calibration via `sources/`, so the validity is traceable. Recalibration produces a new `calibration` product with updated timestamps -- the old one remains unchanged.


### `spectrum` -- Histogrammed / Binned Data

N-dimensional histograms: energy spectra, positron lifetime spectra (PALS), Doppler broadening line shapes, energy-energy coincidence matrices, angular correlations (ACAR), timing resolution curves, and any other binned statistical summary.

Spectra are fundamentally different from volumes (regular spatial grids) and events (per-event tables). They are binned reductions of raw data, often with non-uniform bin edges, and frequently carry fit results alongside the raw histogram.

```
<file>.h5
├── attrs: (common)
│   product: "spectrum"
│   n_dimensions: int                   # 1, 2, 3, ...
│   default: "counts"                   # or "fit/curve" for fitted data
│
├── metadata/
│   method/
│   │   attrs: {_type: "energy" | "lifetime" | "doppler" | "angular" | "timing" | "coincidence_matrix",
│   │           _version: 1,
│   │           description: "..."}
│   │
│   │   # --- _type: "lifetime" (PALS) ---
│   │   attrs: {start_signal: "22Na 1274 keV",
│   │           stop_signal: "annihilation 511 keV"}
│   │   time_resolution/
│   │       attrs: {value: 0.180, units: "ns", unitSI: 1e-9}
│   │   source_activity/
│   │       attrs: {value: 25.0, units: "kBq", unitSI: 1e3}
│   │
│   │   # --- _type: "energy" ---
│   │   attrs: {detector: "HPGe", energy_range: [0, 1500]}
│   │   energy_range/
│   │       attrs: {value: [0, 1500], units: "keV", unitSI: 1.602e-16}
│   │   live_time/
│   │       attrs: {value: 3600.0, units: "s", unitSI: 1.0}
│   │
│   │   # --- _type: "doppler" ---
│   │   attrs: {s_parameter: 0.487, w_parameter: 0.012}
│   │   line_energy/
│   │       attrs: {value: 511.0, units: "keV", unitSI: 1.602e-16}
│   │
│   │   # --- _type: "coincidence_matrix" ---
│   │   attrs: {detector_1: "HPGe_left", detector_2: "HPGe_right"}
│   │   coincidence_window/
│   │       attrs: {value: 10.0, units: "ns", unitSI: 1e-9}
│   │
│   │   # --- _type: "angular" (ACAR) ---
│   │   attrs: {geometry: "1D" | "2D"}
│   │   angular_range/
│   │       attrs: {value: [-30, 30], units: "mrad", unitSI: 0.001}
│   │
│   acquisition/
│       attrs: {total_counts: int,
│               dead_time_fraction: float,
│               description: "Acquisition statistics"}
│       live_time/
│           attrs: {value: float, units: "s", unitSI: 1.0}
│       real_time/
│           attrs: {value: float, units: "s", unitSI: 1.0}
│
├── counts                              # dataset: the histogram itself
│   │                                   # 1D: shape (N_bins,)
│   │                                   # 2D: shape (N_bins_ax0, N_bins_ax1)
│   │                                   # AND: shape (N_bins_ax0, ..., N_bins_axN)
│   attrs: {description: "Binned counts (or rates, or normalized intensity)"}
│
├── counts_errors                       # dataset: same shape as counts (Poisson or propagated)
│   attrs: {description: "Statistical uncertainties on counts (1-sigma)"}
│
├── axes/                               # one sub-group per dimension
│   ax0/
│   │   attrs: {label: "time",          # or "energy", "angle", etc.
│   │           units: "ns",            # or "keV", "mrad", etc.
│   │           unitSI: 1e-9,
│   │           description: "Positron lifetime"}
│   │   bin_edges                       # dataset: float64 (N_bins + 1,)
│   │                                   # supports non-uniform binning
│   │   bin_centers                     # dataset: float64 (N_bins,) -- convenience
│   ax1/                                # 2D+ only
│       attrs: {label: "energy",
│               units: "keV",
│               unitSI: 1.602e-16,      # keV -> J
│               description: "Photon energy"}
│       bin_edges                       # dataset: float64 (M_bins + 1,)
│       bin_centers                     # dataset: float64 (M_bins,)
│
├── fit/                                # optional: fit results
│   attrs: {_type: "multi_exponential" | "gaussian" | "voigt" | "custom",
│           _version: 1,
│           chi_squared: float,
│           degrees_of_freedom: int,
│           description: "Model fit to the spectrum data"}
│   curve                               # dataset: same shape as counts -- the fitted curve
│       attrs: {description: "Evaluated fit function"}
│   residuals                           # dataset: same shape as counts
│       attrs: {description: "Fit residuals (counts - curve)"}
│   components/                         # individual fit components (e.g., lifetime components)
│       component_0/
│           attrs: {label: "free positron",
│                   # parameters depend on _type:
│                   # multi_exponential:
│                   intensity: 0.72, intensity_error: 0.02,
│                   description: "Free positron annihilation component"}
│           lifetime/
│               attrs: {value: 0.382, units: "ns", unitSI: 1e-9}
│           lifetime_error/
│               attrs: {value: 0.005, units: "ns", unitSI: 1e-9}
│           curve                       # dataset: this component's contribution
│       component_1/
│           attrs: {label: "positronium",
│                   intensity: 0.28,
│                   description: "Ortho-positronium component"}
│           lifetime/
│               attrs: {value: 1.85, units: "ns", unitSI: 1e-9}
│           curve
│   parameters/                         # raw parameter table for programmatic access
│       attrs: {names: ["tau_1", "I_1", "tau_2", "I_2", "bg"],
│               values: [0.382, 0.72, 1.85, 0.28, 12.5],
│               errors: [0.005, 0.02, 0.03, 0.02, 0.8],
│               description: "All fit parameters as arrays"}
│
├── sources/
│   raw_data/
│       attrs: {id, product: "listmode", role: "raw_events", ...}
│       --> h5py.ExternalLink(...)
│
├── provenance/
└── extra/
```

**Dimensionality examples:**

| Spectrum type | Dimensions | Axes |
|--------------|------------|------|
| Energy (gamma) | 1D | energy (keV) |
| Positron lifetime (PALS) | 1D | time (ns) |
| Doppler broadening | 1D | energy (keV), centered on 511 keV |
| TOF resolution | 1D | time difference (ns) |
| Energy-energy coincidence | 2D | energy_1 (keV) x energy_2 (keV) |
| Energy-lifetime correlation | 2D | energy (keV) x time (ns) |
| 2D-ACAR | 2D | angle_x (mrad) x angle_y (mrad) |
| Triple-gamma energy | 3D | energy_1 x energy_2 x energy_3 (keV) |

The `axes/` group with explicit `bin_edges` handles non-uniform binning (common in lifetime spectra where bins are often non-linear or rebinned). The `fit/` group with `_type`/`_version` handles the wide variety of fitting models without baking any specific model into the schema.


### `roi` -- Regions of Interest

Label masks, geometric shapes, or contour sets defined on (or applicable to) image data. ROIs are their own product type because they have a many-to-many relationship with images: one image can have multiple ROI sets (different operators, methods, purposes), and one ROI set can be applied to multiple co-registered images.

The `sources/reference_image` link records which image the ROIs were *defined on* (provenance), but does not restrict which images they can be *applied to* (that is an analysis decision, not a storage decision).

```
<file>.h5
├── attrs: (common) + {}
│   product: "roi"
│   timestamp: str                      # when the ROIs were created, not the scan time
│
├── metadata/
│   method/
│   │   attrs: {_type: "manual" | "threshold" | "ai_segmentation" | "atlas" | "geometric",
│   │           _version: 1,
│   │           description: "..."}
│   │
│   │   # --- _type: "manual" ---
│   │   attrs: {tool: "MIM 7.2", operator: "Dr. Smith"}
│   │
│   │   # --- _type: "threshold" ---
│   │   attrs: {threshold_value: 0.41, threshold_type: "relative_max",
│   │           seed_region: "liver", erosion_mm: 2.0}
│   │
│   │   # --- _type: "ai_segmentation" ---
│   │   attrs: {model: "TotalSegmentator", model_version: "2.0.1",
│   │           weights_hash: "sha256:...", task: "total"}
│   │
│   │   # --- _type: "atlas" ---
│   │   attrs: {atlas_name: "AAL3", registration_method: "SyN",
│   │           template_space: "MNI152"}
│   │
│   │   # --- _type: "geometric" ---
│   │   attrs: {coordinate_system: "patient"}
│
├── mask                                # integer label volume, same grid as reference image
│   attrs: {affine: float64[4,4],
│           reference_frame: str,
│           description: "Label mask where each integer maps to a named region"}
│
├── regions/                            # one sub-group per named region
│   <region_name>/
│       attrs: {label_value: int,       # maps to integer in mask dataset
│               color: [R, G, B],       # display color (0-255)
│               description: str,
│               # optional vocabulary links
│               anatomy: str,           # e.g. "liver"
│               anatomy_vocabulary: str, # e.g. "SNOMED CT"
│               anatomy_code: str}      # e.g. "10200004"
│       statistics/                     # optional, computed at creation or later
│           attrs: {n_voxels: int,
│                   computed_on: str,   # id of image used for statistics
│                   description: "ROI statistics"}
│           volume/
│               attrs: {value: float, units: "mL", unitSI: 1e-6}
│           mean/
│               attrs: {value: float, units: str, unitSI: float}
│           max/
│               attrs: {value: float, units: str, unitSI: float}
│           std/
│               attrs: {value: float, units: str, unitSI: float}
│
├── geometry/                           # alternative/complement to mask: parametric shapes
│   <shape_name>/
│       attrs: {shape: "sphere" | "cylinder" | "box" | "ellipsoid",
│               label_value: int,
│               description: str}
│       center/
│           attrs: {value: [x, y, z], units: "mm", unitSI: 0.001}
│       # shape-specific:
│       radius/                             # sphere
│           attrs: {value: float, units: "mm", unitSI: 0.001}
│       dimensions/                         # box
│           attrs: {value: [w, h, d], units: "mm", unitSI: 0.001}
│
├── contours/                           # alternative: per-slice contour vertices
│   attrs: {description: "Per-slice contour coordinates (RT-STRUCT compatible)"}
│   <slice_index>/                      # e.g. "slice_0042"
│       <region_name>                   # dataset: float32 (N, 2) -- vertex coords in-plane
│           attrs: {units: "mm", label_value: int}
│
├── sources/
│   reference_image/
│       attrs: {id, product: "recon", file, content_hash,
│               role: "reference_image",
│               description: "Image on which these ROIs were defined"}
│       --> h5py.ExternalLink(...)
│
├── provenance/
└── extra/
```

**Three representation modes** (not mutually exclusive within one file):

1. **`mask`** -- integer label volume on the same voxel grid as the reference image. Best for dense segmentations (organs, AI output). Compact with gzip since label arrays are low-entropy.
2. **`geometry/`** -- parametric shapes (spheres, cylinders, boxes). Resolution-independent. Best for phantom QC with known coordinates, or simple clinical VOIs.
3. **`contours/`** -- per-slice vertex lists. Best for clinical contours (RT-STRUCT style). Preserves the original drawing fidelity at any resolution.

A single ROI file can contain all three: a `mask` for fast voxel-level operations, `geometry/` for the original shape definitions, and `contours/` for RT-STRUCT export compatibility.

**Statistics are optional and attributed.** If statistics are computed at ROI creation time, they are stored in `regions/<name>/statistics/` with a `computed_on` attribute recording which image was used. If statistics are computed later in an analysis pipeline, that is the analysis output's responsibility -- not the ROI file's.

**The `_type`/`_version` on `method/`** handles the full range of ROI creation methods:

| `_type` | Meaning | Key attributes |
|---------|---------|----------------|
| `manual` | Operator drew contours | `tool`, `operator` |
| `threshold` | Semi-automatic thresholding | `threshold_value`, `threshold_type`, `seed_region` |
| `ai_segmentation` | Fully automatic ML model | `model`, `model_version`, `weights_hash`, `task` |
| `atlas` | Atlas-based parcellation | `atlas_name`, `registration_method`, `template_space` |
| `geometric` | Coordinate-based shapes | `coordinate_system` |

New methods (e.g., `interactive_watershed`, `diffusion_model`, `foundation_model`) just add a new `_type` value. No schema change, no re-export of existing ROIs.


### `device_data` -- Device Signals and Acquisition Logs

Time-series data from acquisition devices: ECG monitors, motion trackers, infusion pumps, blood samplers, environmental sensors. Covers both **embedded** device data (small, tightly-coupled, stored inside `listmode` or `recon` files) and **standalone** device data products (large or shared streams with independent identity).

```
<file>.h5
├── attrs: (common)
│   product: "device_data"
│   device_type: str                  # high-level category (see table)
│   device_model: str                 # e.g. "Anzai AZ-733V", "Syringe Pump SP101"
│   recording_start: str              # ISO 8601
│
├── recording_duration/
│   attrs: {value: float, units: "s", unitSI: 1.0}
│
├── metadata/
│   device/
│       attrs: {_type: "blood_sampler" | "motion_tracker" | "infusion_pump"
│                      | "physiological_monitor" | "environmental_sensor",
│               _version: 1, description: "..."}
│
├── channels/                          # one sub-group per signal channel (NXlog pattern)
│   <channel_name>/
│       attrs: {_type, _version, model, measurement, run_control, description}
│       sampling_rate/
│           attrs: {value: float, units: "Hz", unitSI: 1.0}
│       signal              # dataset: float64 (N,)
│           attrs: {units, unitSI, description}
│       time                # dataset: float64 (N,)
│           attrs: {units: "s", unitSI: 1.0, start: str}
│       average_value       # optional: float
│       minimum_value       # optional: float
│       maximum_value       # optional: float
│       duration/           # optional
│           attrs: {value: float, units: "s", unitSI: 1.0}
│       cue_timestamp_zero  # optional: coarse timestamps for random access
│       cue_index           # optional: indices into time/signal
│
├── sources/                           # links to acquisition this device data belongs to
├── provenance/
│   original_files                    # compound dataset: (path, sha256, size_bytes)
│   ingest/
│       attrs: {tool, tool_version, timestamp, description}
└── extra/
```

**Device types:**

- `blood_sampler` -- arterial/venous blood sampling for kinetic input functions
- `motion_tracker` -- external motion tracking (optical, electromagnetic)
- `infusion_pump` -- contrast/tracer infusion profiles
- `physiological_monitor` -- ECG, respiratory, SpO2, blood pressure, core temperature
- `environmental_sensor` -- room temperature, humidity, detector temperature, air quality

**NXlog/NXsensor pattern**: Each channel follows the NeXus NXlog convention (time + signal arrays, summary statistics, optional cue index for random access into long series) enriched with NXsensor metadata fields (`model`, `measurement` enum, `run_control` boolean indicating whether acquisition was synchronized to this signal).

**Embedding vs. standalone rule**:
- **Embed** device data that is (1) specific to this one product, (2) small (< ~10 MB), and (3) needed to interpret the product (e.g., ECG for gating, detector temperature for QC)
- **Link** device data that is (1) large, (2) shared across products, or (3) has independent provenance (e.g., blood sampling curve, external motion tracking that spans multiple bed positions)


## Derived Outputs

The `fd5` package can generate human-readable companion files from the HDF5 data. These are **derived, not canonical**. Delete them and regenerate at any time.

### manifest.toml

A lightweight, human-readable index of all data products in a dataset directory. Used for quick queries ("what scans exist?", "what time range?") without opening any HDF5 files. Generated by `fd5.manifest.write_manifest()` or `fd5.manifest.rebuild_from_h5()`.

```toml
_schema_version = 1
dataset_name = "dd01"

[study]
type = "clinical"

[subject]
species = "human"
birth_date = "1959-03-15"

[[data]]
product = "recon"
id = "sha256:2a3ac438e7f1b9d0..."    # full hash; filenames use first 8 chars
file = "data/2024-07-24_19-06-10_recon-2a3ac438_pet_qclear_wb.h5"
scan_type = "pet"
timestamp = "2024-07-24T19:06:10+02:00"
z_min_mm = -850.0
z_max_mm = -12.5
duration_s = 367.0
has_volume = true
has_mip_coronal = true
sources = ["sha256:def67890...", "sha256:21d255e7..."]  # listmode + CTAC

[[data]]
product = "roi"
id = "sha256:aabb1122c4d5e6f7..."
file = "data/2024-07-24_19-06-10_roi-aabb1122_pet_tumor_contours.h5"
scan_type = "pet"
timestamp = "2026-01-15T10:30:00+01:00"
method = "manual"
n_regions = 3
sources = ["2a3ac438"]
```

### datacite.yml

Dataset-level metadata for discovery by data catalogs and AI search agents. Generated by `fd5.datacite.generate()` from the manifest and HDF5 metadata.

```yaml
title: "DOGPLET DD01 -- Dual-tracer PET/CT"
creators:
  - name: "..."
    affiliation: "..."
dates:
  - date: "2024-07-24"
    dateType: "Collected"
resourceType: "Dataset"
subjects:
  - subject: "PET/CT"
    subjectScheme: "DICOM Modality"
  - subject: "FDG"
    subjectScheme: "Radiotracer"
```

### ro-crate-metadata.json

A JSON-LD file conforming to the RO-Crate 1.2 specification, describing the dataset as a Research Object. Generated by `fd5.rocrate.generate()` from the manifest, HDF5 metadata, and study/creators information.

The generator maps fd5 vocabulary to Schema.org terms:

- `study/license` → `license`
- `study/creators/` → `author` (as `Person` entities with `affiliation` and `@id` from ORCID)
- `id` → `identifier` (as `PropertyValue` with `propertyID: "sha256"`)
- `timestamp` → `dateCreated` per file
- `provenance/ingest/` → `CreateAction` with `SoftwareApplication` instrument
- `sources/` DAG → `isBasedOn` references between data entities
- Each `.h5` file → `File` (MediaObject) with `encodingFormat: "application/x-hdf5"`

Example snippet:

```json
{
  "@context": "https://w3id.org/ro/crate/1.2/context",
  "@graph": [
    {
      "@id": "ro-crate-metadata.json",
      "@type": "CreativeWork",
      "about": {"@id": "./"},
      "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2"}
    },
    {
      "@id": "./",
      "@type": "Dataset",
      "name": "DOGPLET DD01",
      "license": "CC-BY-4.0",
      "author": [
        {
          "@type": "Person",
          "name": "Jane Doe",
          "affiliation": "ETH Zurich",
          "@id": "https://orcid.org/0000-0002-1234-5678"
        }
      ],
      "hasPart": [
        {"@id": "2024-07-24_19-06-10_recon-2a3ac438_pet_qclear_wb.h5"}
      ]
    }
  ]
}
```

### Schema dump

The embedded `_schema` attribute can be extracted to a standalone JSON Schema file for documentation or validation tooling:

```bash
fd5 schema-dump data/2024-07-24_19-06-10_recon-2a3ac438_pet_qclear_wb.h5 > schema.json
```


## Scope and Non-Goals

`fd5` defines **what a clean, immutable data product looks like**. It does not define how to get there.

**In scope (the fd5 core):**
- HDF5 schema conventions and attribute patterns (units, types, versions, descriptions)
- Write-once file creation with streaming hash computation
- Content hashing (Merkle tree) and integrity verification
- Provenance DAG conventions (`sources/`, `provenance/`)
- Schema embedding and validation (JSON Schema)
- `h5_to_dict` / `dict_to_h5` round-trip helpers
- TOML manifest generation and parsing
- Datacite metadata and RO-Crate JSON-LD generation
- Filename generation
- Product schema registration and discovery

**In scope (domain schema packages):**
- Domain-specific product schemas (e.g., `fd5-imaging` for `recon`/`listmode`/`sinogram`, `fd5-genomics` for `alignment`/`variants`/`expression`)
- Domain-specific vocabulary references
- Domain-specific `id_inputs` conventions

**Out of scope (handled by domain-specific ingest/processing packages):**
- Parsing vendor-specific or instrument-specific formats (DICOM, FASTQ, vendor binaries)
- Data processing and analysis (reconstruction, alignment, variant calling)
- Ingest pipeline orchestration
- Dataset discovery from raw instrument directories

The boundary is clean: a domain-specific ingest or processing pipeline produces `fd5` files. From that point forward, the fd5 core handles everything -- regardless of domain.

**Ingest coupling:** While ingest pipelines are out of scope for the fd5 package, **the fd5 product schema is effectively the ingest contract**. The schema defines exactly which source fields become metadata attributes, how datasets are structured, what units convention to follow, and what provenance to record. Ingest pipelines are written *against* the fd5 schema. This coupling is intentional and healthy -- it means the schema drives the ingest design, not the other way around. A well-defined fd5 product schema is a specification that multiple ingest implementations can target, regardless of the upstream format.


## Design Discussion

### Device data placement: embedding vs. linking

Device data from acquisition systems (ECG monitors, motion trackers, infusion pumps, environmental sensors) can be managed in three ways, each with trade-offs:

**Option A: Always embed.** Store all device data directly inside the `listmode` or `recon` file as a `device_data/` group. Advantages: self-contained files with no external links, full provenance captured with the acquisition. Disadvantages: bloats files (if device data is large or sampled at high rates), prevents sharing a single device stream across multiple products (e.g., one arterial input function used in multiple kinetic models), and couples independent data streams into single files.

**Option B: Always separate.** Create standalone `device_data` product files for all device streams, similar to how ROIs are separate from reconstructions. Advantages: clean separation of concerns, enables sharing data across products via `sources/` links, and keeps individual files smaller. Disadvantages: file proliferation ("too many files"), broken links if a device file moves, and ambiguity about whether a device stream is "part of this acquisition" or "shared infrastructure."

**Option C: Hybrid (chosen).** Embed device data that is (1) specific to this one product, (2) small (<~10 MB), and (3) needed to interpret the product (e.g., cardiac gating signal, detector temperature for QC). For large or shared streams (e.g., arterial input functions, external motion tracking spanning multiple bed positions), create standalone `device_data` products and link them via `sources/`. This combines the benefits of self-containment (small, coupled data) and reusability (large, shared data).

**Rationale:** fd5 files are write-once archives. Once a reconstruction is finalized, its device context (gating, temperatures) is frozen. But acquisition devices (blood samplers, motion trackers) often record continuously during long scans or produce data shared across multiple reconstructions. The hybrid model accommodates both patterns without forcing a compromise.

### NeXus base class adoption

A systematic review of NeXus base classes identified several patterns worth adopting into fd5:

**Adopted:**
- **NXcollection** → `extra/` group for unvalidated, vendor-specific, or experimental data
- **NXdata** → Default visualization chain (implicitly followed via dataset naming conventions)
- **NXlog** → Device data channels with time + signal arrays, summary statistics, and cue indices for random access
- **NXsensor** → Device metadata fields (model, measurement type, run_control) on each channel
- **NXcite** → Literature references (`references/` sub-group under metadata describing algorithms/methods)
- **NXnote** → Binary attachments in `extra/notes/` (screenshots, PDFs) with MIME typing and authorship

**Not adopted and why:**
- **NXinstrument, NXsource, NXdetector** → Redundant with fd5's simpler `metadata/acquisition/` and `metadata/corrections/` structure
- **NXtransformations** → Axis alignment is handled by explicit `affine` attributes on volume datasets
- **NXmonitor** → Not applicable to fd5's write-once model; monitoring is a runtime concern during acquisition
- **NXenvironment** → Subsumed by `device_data/environmental_sensor`
- **NXsubentry, NXuser, NXparameters, NXgeometry** → Either too hierarchical for fd5's flat product model or domain-specific to specific NeXus facilities

The adoption is pragmatic: fd5 borrows patterns that reduce ambiguity (NXlog/NXsensor for device data) and enable FAIR practices (NXcite for method references, NXnote for supplementary materials), while keeping the overall schema lean.

### RO-Crate and FAIR readiness

fd5 can export to RO-Crate 1.2 JSON-LD with minimal additions to the schema. Two fields were added to the `study/` group:

- **`license`**: SPDX identifier or URL (e.g., `"CC-BY-4.0"`, `"CC0-1.0"`). Required by RO-Crate on the Root Data Entity.
- **`creators/`**: Sub-group with author metadata (name, affiliation, ORCID, role). Enables Schema.org `Person` entity mapping.

With these fields, `fd5.rocrate.generate()` produces a conformant `ro-crate-metadata.json` that maps fd5 vocabulary to Schema.org terms:
- Study license → RO-Crate license
- Study creators → RO-Crate author (Person entities)
- File IDs → identifier (PropertyValue with propertyID: sha256)
- Provenance ingest records → CreateAction with instrument
- Sources DAG → isBasedOn references

This enables discovery by major FAIR registries (FAIRshare, DataCite, Zenodo) without requiring fd5 files to be converted to other formats. The RO-Crate is a derived output, like `manifest.toml` and `datacite.yml` -- regenerable at any time from the HDF5 metadata.

### HDF5 cloud compatibility for fd5

fd5 is designed for **local-first and batch-cloud** workflows. It is not cloud-optimized for interactive tile streaming, and that is intentional.

**Design rationale:**

- **Semantic atomicity**: fd5 products (reconstructions, listmode data, spectra) are semantically atomic -- the typical access pattern is full-volume load plus metadata, not tile-by-tile streaming. You *want* one coherent file per product, not thousands of chunk files scattered across an object store.

- **Sequential reads**: Scientific workflows are dominated by sequential, row-based reads: load a volume slice-by-slice, scan an event table, iterate over spectral bins. fd5's chunking strategy (e.g., `(1, Y, X)` for slice-wise access, row-based chunks for tables) is optimized for this write-once, sequential-read pattern.

- **Two-step schema discovery**: The `_schema` attribute enables efficient metadata-first workflows: (1) read `_schema` (one range request, lightweight), (2) decide which datasets to fetch, (3) read targeted datasets. This is fast and explicit.

- **Derived outputs for discovery**: The manifest (`manifest.toml`), datacite metadata (`datacite.yml`), and RO-Crate (`ro-crate-metadata.json`) provide zero-latency discovery for cloud/catalog scenarios. These are the lightweight index layer; the HDF5 files are the data layer.

**HDF5 over cloud storage:**

HDF5's ros3 VFD supports HTTP range requests, enabling incremental reads from S3. A single-slice read from a chunked volume requires one range request per chunk. For fd5's typical product sizes (100 MB -- 1 GB, hundreds to thousands of chunks), this is efficient for batch workflows (download-then-process, parallel job submission).

**Honest limitation:** HDF5's B-tree metadata traversal requires multiple sequential range requests before locating a chunk. Over high-latency connections, this adds latency compared to Zarr's deterministic chunk addressing. For fd5's use case (batch processing, local NFS, POSIX filesystems), this trade-off is acceptable. The semantic atomicity and single-file simplicity outweigh the latency cost.

**Where Zarr excels:** Zarr's strengths (massively parallel writes across N workers, browser-friendly tile serving, trivial per-chunk CDN caching) are outside fd5's design goals. fd5 is write-once, batch-oriented, and designed for scientific workflows, not interactive web visualization.

### Relationship to RDF and the Semantic Web

A natural question is why fd5 uses embedded JSON Schema and flat vocabulary references rather than RDF triples and OWL ontologies for its metadata layer.

**The short answer:** fd5 and RDF operate at different layers. fd5 is a data-product format (Layer 1: files containing data + metadata). RDF is a knowledge-representation framework (Layer 3: a graph of statements linking entities across datasets, institutions, and domains). They are complementary, not competing.

```
Layer 3:  Knowledge graph / federation    ← RDF, SPARQL, OWL ontologies
Layer 2:  Dataset-level metadata index    ← RO-Crate JSON-LD (fd5 exports this)
Layer 1:  Data product (file-level)       ← fd5 / HDF5
Layer 0:  Raw instrument output           ← DICOM, FASTQ, vendor formats
```

**Why fd5 does not use RDF internally:**

1. **Self-containment.** An fd5 file must be fully understandable offline, on a laptop, with no network and no triplestore. Embedding RDF triples inside HDF5 attributes adds complexity (turtle/JSON-LD serialization, namespace resolution, ontology imports) without improving the core use case: a scientist or AI agent reading `h5dump -A` to understand the file.

2. **Audience.** fd5's primary users are scientists and automated pipelines -- not semantic web developers. JSON Schema, `description` strings, and `__units` attributes are immediately comprehensible. OWL class hierarchies and SPARQL are not.

3. **Write-once integrity.** fd5's Merkle-tree `content_hash` covers data and metadata together in a single sealed file. RDF triplestores are mutable graphs with no inherent content-addressed integrity.

4. **Complexity budget.** The simplest metadata representation that supports AI-readability, FAIR compliance, and domain extensibility is the right one. fd5's conventions (`_type`/`_version`, `_vocabulary`/`_code`, `description`, `__units`/`__unitSI`) achieve this without the overhead of a full semantic web stack.

**How fd5 bridges to the RDF world:**

- The `ro-crate-metadata.json` derived output is JSON-LD -- a valid RDF serialization. It maps fd5 vocabulary to Schema.org terms (`Person`, `Dataset`, `CreateAction`, `isBasedOn`).
- Vocabulary references (`_vocabulary` / `_code` attributes) use human-readable names from standard terminologies that have well-known URI mappings in BioPortal and other ontology registries.
- A triplestore can ingest the RO-Crate JSON-LD from a collection of fd5 datasets to build a federated, SPARQL-queryable knowledge graph -- without fd5 itself needing to speak RDF natively.
- The `sources/` provenance DAG maps naturally to PROV-O (`wasDerivedFrom`, `wasGeneratedBy`) in the RO-Crate export.

The design philosophy is: **store data and metadata together in a simple, self-describing binary format (HDF5); export metadata to the Linked Data ecosystem as a derived representation (RO-Crate JSON-LD).** This keeps the file format accessible to domain scientists and automated pipelines while enabling full FAIR discoverability for semantic web infrastructure.


## Comparison with Existing Formats

| Format | Strengths | Gaps that fd5 addresses |
|--------|-----------|------------------------|
| **NeXus/HDF5** | Mature, `@units`, `default` chain, `NXcollection`, `NXlog`/`NXsensor` for device data, `NXcite` for references, `NXnote` for attachments | Tied to neutron/X-ray facility domain; fd5 adopts NeXus patterns selectively as domain-agnostic conventions |
| **OpenPMD** | `unitSI`, mesh/particle duality | Focused on particle-in-cell simulations; no general-purpose product schema extensibility |
| **BIDS** | Self-describing filenames, metadata inheritance, sidecar JSON | Tied to neuroimaging (MRI/EEG); filenames encode too much; no write-once integrity |
| **NIfTI** | Simple, widely supported for volumes | No metadata beyond affine; no provenance; no non-volume data |
| **DICOM** | Comprehensive tags, universal in clinical imaging | Verbose, inconsistent across vendors, poor for non-image data, mutable, no content hashing |
| **ROOT/TTree** | Excellent for event data, schema evolution | C++ ecosystem; poor Python ergonomics; no self-describing metadata conventions |
| **Zarr v3** | Cloud-native chunked storage, parallel I/O, per-chunk independence | Storage engine only; no metadata conventions, no provenance, no schema embedding, no immutability guarantee |
| **SOME-Zarr (NGFF)** | Multiscale pyramids, cloud-optimized bioimaging, growing tool ecosystem | Microscopy-focused; no event data, spectra, or calibration; no embedded schema; no provenance DAG; no per-product identity |
| **RO-Crate** | Standard for packaging research objects, Schema.org JSON-LD, FAIR compatible, increasingly supported by repositories | Not a data storage format; no domain-specific schemas; fd5 generates RO-Crate as derived output for metadata discovery |
| **RDF / Linked Data** | Web-scale semantic interoperability, ontology-driven reasoning (OWL), federated SPARQL queries across institutions, native language of FAIR registries | Not a data storage format -- stores statements *about* data, not the data itself; requires triplestore infrastructure; no self-contained offline files; no integrity hashing; high complexity barrier for domain scientists |

`fd5` takes the best ideas from each:
- `@units` + `@unitSI` from NeXus and OpenPMD
- `default` attribute chain from NeXus
- `extra/` unvalidated collection from NeXus (`NXcollection`)
- Human-readable filenames inspired by BIDS (but freeform, not key-value)
- `_type`/`_version` extensibility inspired by NeXus `NXentry` typing and ROOT schema evolution
- ISO 8601 with timezone from NeXus best practices
- `_errors` suffix convention from NeXus
- Multiscale resolution pyramids inspired by SOME-Zarr NGFF (adapted to HDF5's single-file model)
- Per-chunk content hashing inspired by Zarr's per-chunk integrity model (rolled up into a Merkle tree)
- Content hashing from scientific reproducibility best practices
- Device data channels with time + signal arrays from NeXus `NXlog` pattern
- Device metadata (model, measurement, run_control) from NeXus `NXsensor`
- Literature references in `references/` groups from NeXus `NXcite`
- Binary attachments with MIME typing in `extra/notes/` from NeXus `NXnote`
- RO-Crate JSON-LD as the bridge to the RDF/Linked Data ecosystem (fd5 files are self-contained HDF5; their metadata is discoverable as RDF via derived RO-Crate export)
- Write-once immutability from content-addressed storage systems (Git, IPFS)


## FAIR Compliance Summary

| FAIR Principle | fd5 Feature |
|----------------|-------------|
| **F1**: Globally unique identifier | `id` -- algorithm-prefixed SHA-256 of identity inputs, stable across re-ingests |
| **F2**: Rich metadata | `metadata/` group tree, `description` on every group/dataset |
| **F3**: Metadata includes identifier | `id` is a root attribute in every file |
| **F4**: Registered in searchable resource | `manifest.toml` as local index; `datacite.yml` for catalog registration |
| **A1**: Retrievable by identifier | Direct file access; manifest maps id to file path; RO-Crate JSON-LD for linked data discovery |
| **A1.1**: Open, free protocol | HDF5 = open standard; h5py = open source |
| **A2**: Metadata accessible even if data unavailable | Manifest contains all metadata; `h5dump -A` extracts attrs without data; RO-Crate JSON available without HDF5 read |
| **I1**: Formal, shared knowledge representation | JSON Schema embedded; `@units`/`@unitSI`; vocabulary references; RO-Crate JSON-LD using Schema.org |
| **I2**: FAIR vocabularies | Domain-specific vocabulary references via `_vocabulary`/`_code` (e.g., DICOM Modality, SNOMED CT, Sequence Ontology, HGNC) |
| **I3**: Qualified references | `sources/` with typed roles (e.g., `emission_data`, `reference_genome`, `calibration`) |
| **R1**: Rich, plurality of attributes | Three metadata layers: flat root attrs, structured `metadata/` groups, original source headers in `provenance/` |
| **R1.1**: Clear usage license | `study/license` (SPDX identifier); propagated to datacite and RO-Crate exports |
| **R1.2**: Detailed provenance | `sources/` DAG + `provenance/original_files` with SHA-256 hashes |
| **R1.3**: Meet domain standards | NeXus/OpenPMD conventions; domain-specific vocabulary references; RO-Crate JSON-LD for Linked Data interoperability |

### AI-Readability

| Capability | fd5 Feature |
|------------|-------------|
| Schema discovery | `_schema` root attribute (JSON Schema) |
| Content understanding | `description` on every group and dataset |
| Unit interpretation | Sub-group pattern for attributes: `<name>/{value, units, unitSI}`; dataset attrs for datasets: `units`/`unitSI` |
| Vocabulary resolution | `_vocabulary` + `_code` attributes |
| Auto-visualization | `default` attribute chain to best dataset |
| Provenance tracing | `sources/` group with typed links |
| Integrity verification | `content_hash` on root and source references |


## Versioning

The `_schema_version` attribute on every file root is a monotonically increasing integer. The fd5 package maintains a mapping from version numbers to JSON Schema documents.

**Version contract:**
- New versions only ADD attributes and groups
- Existing attributes and groups are never removed or renamed
- A reader for version N can always read version N-1
- A reader encountering a version newer than it understands logs a warning and reads what it can
- The `_type`/`_version` mechanism handles evolution within polymorphic sub-groups independently of the top-level schema version

### Migration and upgrades

**Content hash stability:** The `content_hash` is the Merkle root computed from data + attrs. Adding metadata attributes (e.g., during schema upgrade) changes the `content_hash` because the file content has changed. This is expected and correct -- the file is a new version of the same product (same `id`, new `content_hash`).

**Per-dataset data hashes remain stable** if only metadata changes. The Merkle tree structure means that adding attributes to a group changes the group hash and propagates up to the root, but the dataset hashes (which depend only on the data chunks) remain unchanged. This enables efficient verification: re-hash only the changed metadata, not the data.

**Migration is copy-on-write:** Schema upgrades produce a new file with the upgraded schema, same `id`, new `content_hash`. The old file can be archived or deleted. There is no in-place modification (fd5 files are immutable after creation -- see Immutability and concurrency section).

**SDK migration tool:** The fd5 package provides `fd5.migrate(old_path, new_path, target_version)` which:
1. Copies all data datasets from old to new (zero-copy via HDF5 virtual datasets where possible)
2. Copies all existing metadata
3. Adds new required attributes with sensible defaults (or prompts for values)
4. Recomputes `content_hash` (fast: ms-scale for metadata-only changes, seconds for full data re-hash on typical products)

**Forward compatibility:** The `_schema_version` attribute on each file tells readers exactly what to expect. Readers encountering a newer version than they support log a warning and read what they can (additive-only guarantee). If a reader requires a specific version, it can check `_schema_version` and refuse to open.

**Re-hashing performance:** Re-hashing a file is fast by design:
- Metadata-only changes: ms-scale (hash only the changed attributes)
- Full data re-hash: seconds for typical products (100 MB -- 1 GB), with per-chunk hashing enabling incremental verification

### Immutability and concurrency

fd5 files are **immutable after creation**. This design decision enables simple concurrency semantics, reliable provenance, and content-addressable storage.

**Write-once model:**

The file creation process is a single atomic operation:
1. Open file for writing
2. Write all data, metadata, and hashes (streaming hash computation, see Write-time workflow)
3. Close file
4. File is sealed -- never modified again

**No in-place edits:** Any change to data or metadata produces a **new file** (copy-and-replace). The new file gets a new `content_hash` but keeps the same `id` if the identity inputs haven't changed (e.g., same scan, different processing). Old versions can coexist for archival or comparison.

**SDK enforcement:** The fd5 SDK enforces immutability via a builder/context-manager API:

```python
with fd5.create(path, product="recon", ...) as f:
    f.write_volume(data)
    f.write_metadata(metadata_dict)
    # On context exit: Merkle root finalized, content_hash written, file sealed
```

There is no `fd5.open_for_edit()` or `fd5.append()`. Once the context exits, the file is immutable.

**Concurrency semantics:**

- **Concurrent reads are safe**: HDF5 supports multiple readers on immutable files with no locking concerns. The write-once guarantee means readers never see partial writes or inconsistent state.

- **Single writer during creation**: The creation process is single-threaded (one Python process writes the file). Parallelism happens *across* files, not within them (e.g., N worker processes creating N reconstruction files in parallel).

- **HDF5 SWMR is not used**: Single Writer Multiple Reader (SWMR) mode is designed for append workflows (e.g., live data acquisition writing to a file that readers monitor). fd5 does not support append -- files are created once and sealed.

- **Hashing is live during creation**: Hash computation happens inline as data is written (see Write-time workflow). There is no post-creation reopen or locking. The `content_hash` is finalized just before file close, and the file becomes immutable at close time.

**Implications:**

- **Content-addressable storage**: Immutable files with stable `content_hash` values can be stored in content-addressable systems (e.g., DataLad, git-annex, IPFS) without special handling.

- **Reliable provenance**: The `sources/` DAG references immutable products. A `content_hash` mismatch definitively indicates data corruption or substitution.

- **Simplified archival**: No need to track "latest version" -- each file is a complete, immutable snapshot. Archives can safely hard-link or deduplicate identical files.


## Implementation Notes

Concrete decisions for the `fd5` Python package implementation.

### `h5_to_dict` / `dict_to_h5` type mapping

These two functions are the foundation of all metadata I/O. They must handle every Python type that can appear in metadata and round-trip correctly.

**`dict_to_h5(group, d)` -- writing:**

| Python type | HDF5 storage | Notes |
|---|---|---|
| `dict` | Sub-group (recursive) | Keys become group names |
| `str` | Attr (UTF-8 string) | |
| `int` | Attr (int64) | |
| `float` | Attr (float64) | |
| `bool` | Attr (numpy.bool_) | h5py stores as numpy bool |
| `list[int\|float]` | Attr (numpy array) | Homogeneous numeric lists |
| `list[str]` | Attr (vlen string array) | `h5py.special_dtype(vlen=str)` |
| `list[bool]` | Attr (numpy bool array) | |
| `None` | Attr absent (skip) | Absence = None on read |
| `numpy.ndarray` | **Dataset** (not attr) | Anything > 1D or > ~1000 elements |
| `bytes` | Attr (opaque) | Rare; for binary blobs |

**Decision: attr vs. dataset boundary.** Scalars, short lists (<= 1000 elements), and strings go as **attrs**. Numpy arrays and anything large go as **datasets**. The threshold is a pragmatic choice -- attrs are fast to read in bulk (`h5dump -A`), datasets are chunked and compressible.

**`h5_to_dict(group)` -- reading:**

| HDF5 type | Python type | Notes |
|---|---|---|
| Sub-group | `dict` (recursive) | |
| String attr | `str` | |
| Scalar int attr | `int` | Cast from numpy.int64 |
| Scalar float attr | `float` | Cast from numpy.float64 |
| Scalar bool attr | `bool` | Cast from numpy.bool_ |
| Array attr (numeric) | `list[int\|float]` | `.tolist()` |
| Array attr (string) | `list[str]` | |
| Absent attr | `None` | Caller handles missing keys |
| Dataset | **skipped** | Not included in dict; accessed separately |

**Key rule: `h5_to_dict` only reads attrs, never datasets.** Datasets hold large data (volumes, tables, MIPs) and are accessed explicitly. The dict representation is metadata only.

**Reserved attr prefixes:** Attrs starting with `_` (`_type`, `_version`, `_schema`, `_schema_version`) are included in the dict. Sub-groups representing physical quantities (with `value`, `units`, `unitSI` attrs) are included as groups in the dict tree.

### `id` computation

The `id` is a SHA-256 hash of identity inputs, prefixed with `"sha256:"`. The identity inputs are **product-type-specific** and defined by each domain schema. The guiding principle is: **the same logical data product, re-ingested or reprocessed, should produce the same `id`** -- even if the fd5 schema version, compression, or file layout changes.

**Serialization format:** concatenate the input fields with `\0` (null byte) separator, encode as UTF-8, compute SHA-256. The `id_inputs` attr stores a human-readable description of what was hashed (e.g., `"timestamp + instrument_id + vendor_series_id"`).

**Examples from the medical imaging domain:**

| Product type | Identity inputs | Rationale |
|---|---|---|
| `recon` | `timestamp + scanner_uuid + vendor_series_id` | Same acquisition on same scanner = same identity |
| `listmode` | `timestamp + scanner_uuid + vendor_series_id` | Same as recon |
| `sim` | `simulation_config_hash + random_seed` | Same config + seed = same simulation |
| `transform` | `source_id + target_id + method_type + creation_timestamp` | Same inputs + method = same transform |
| `calibration` | `scanner_uuid + calibration_type + valid_from` | Same scanner + type + time = same calibration |
| `spectrum` | `source_id + method_type + creation_timestamp` | Derived from specific data + method |
| `roi` | `reference_image_id + method_type + creation_timestamp` | Drawn on specific image at specific time |

**For new domains,** the same pattern applies: choose identity inputs that capture "what makes this product logically the same thing." For genomics, an alignment product might use `sample_id + reference_genome + aligner_version + run_id`. For remote sensing, a raster product might use `satellite + acquisition_time + band + processing_level`.

**`instrument_id`:** a stable identifier for the source instrument. Domain-specific: for medical scanners this might be `StationName + DeviceSerialNumber`; for sequencers, `instrument_serial + run_id`; for simulations, absent. The `id_inputs` attr documents exactly what was used.

**Filenames use the first 8 hex chars** of the hash (after the `"sha256:"` prefix). Collision risk at 8 chars (32 bits) is negligible for datasets with < 10,000 products.

### `content_hash` computation -- Merkle tree with per-chunk hashing

The `content_hash` is a deterministic hash of the file's content, independent of HDF5 internal layout. It is computed bottom-up: individual HDF5 chunks are hashed first, chunk hashes roll up into per-dataset hashes, and dataset hashes roll up into the file-level Merkle root.

This two-level design (inspired by Zarr's per-chunk integrity model) enables both **full-file verification** and **partial integrity checks** on individual datasets or even individual chunks -- critical for large volumes where re-hashing the entire file is expensive.

#### Per-chunk hashing

Every chunked dataset carries an optional companion dataset `<name>_chunk_hashes` that stores one SHA-256 hash per HDF5 chunk:

```
volume                              # dataset: float32 (300, 512, 512), chunks (1, 512, 512)
volume_chunk_hashes                 # dataset: bytes (300,) -- one SHA-256 per chunk
    attrs: {
        algorithm: "sha256",
        chunk_shape: [1, 512, 512],
        description: "Per-chunk content hashes for partial integrity verification"
    }
```

Each chunk hash is computed as `sha256(chunk_data.tobytes())` where `chunk_data` is the decompressed, row-major byte content of that chunk. Edge chunks (at dataset boundaries where the chunk extends beyond the data) are hashed on the **actual data only** (not zero-padded to full chunk size).

The chunk hash dataset is a 1D array with one entry per chunk, indexed in row-major chunk order (C order over the chunk grid). For a 3D dataset with chunk grid shape `(N_z, N_y, N_x)`, chunk `(i, j, k)` maps to index `i * N_y * N_x + j * N_x + k`.

#### Dataset hash (from chunk hashes)

The `dataset_hash` is computed from the ordered concatenation of all chunk hashes, not from the raw data bytes. This means the dataset hash can be computed from the chunk hash table without re-reading the data:

```
dataset_hash(d) = sha256(
    chunk_hash_0 + chunk_hash_1 + ... + chunk_hash_N
)
```

For non-chunked datasets (scalars, small arrays stored contiguously), the dataset hash falls back to `sha256(d[...].tobytes())`.

#### File-level Merkle tree

The file-level `content_hash` is the Merkle root computed from dataset hashes and attribute hashes:

```
content_hash = sha256(root_group_hash)

group_hash(g) = sha256(
    sorted_attrs_hash(g) +
    for each child in sorted(g.keys()):
        if child is dataset: dataset_hash(child)
        if child is group:   group_hash(child)
)

sorted_attrs_hash(g) = sha256(
    for each key in sorted(g.attrs.keys()):
        if key in ("content_hash", *_chunk_hashes keys): skip
        sha256(key.encode() + serialize(g.attrs[key]))
)
```

The `_chunk_hashes` companion datasets are **excluded from the Merkle tree** (they are derived from the data, not independent content). This avoids circular dependencies and ensures the `content_hash` is identical whether or not chunk hashes are present.

#### Properties

- **Deterministic**: same data + same attrs = same hash, regardless of HDF5 internal layout, chunk boundaries, or compression settings
- **Exclude `content_hash` attr**: the hash doesn't include itself (circular dependency)
- **Exclude `_chunk_hashes` datasets**: derived integrity data, not independent content
- **Row-major byte order**: `chunk_data.tobytes()` produces the same bytes regardless of on-disk compression
- **Sorted keys**: both attrs and child groups are iterated in sorted order for determinism
- **Composable**: the file-level hash can be recomputed from per-dataset hashes without touching the raw data; per-dataset hashes can be recomputed from per-chunk hashes without reading the full dataset

#### Verification at three levels

| Level | What it checks | Cost | Use case |
|-------|---------------|------|----------|
| **File-level** (`content_hash`) | Entire file integrity | Read all data + all attrs | Archival verification, transfer validation |
| **Dataset-level** (`dataset_hash` from chunk table) | Single dataset integrity | Read chunk hash table only | Quick check after partial access |
| **Chunk-level** (`_chunk_hashes`) | Individual chunk integrity | Read one chunk | Diagnose corruption, verify partial downloads |

Partial verification workflow: to check whether `volume` is intact without reading the full file, read `volume_chunk_hashes`, re-hash each chunk of `volume`, compare. To check a single slice (chunk), re-hash just that chunk and compare against the corresponding entry in the hash table.

#### Write-time workflow

The fd5 SDK uses an **online / streaming hash** design where hashes are computed incrementally during file creation, not in a post-processing pass. This is single-pass, crash-safe by construction, and eliminates the need to reopen files.

**Streaming write workflow:**

1. Open the file for writing and initialize the Merkle tree accumulator
2. For each dataset:
   - Write data chunk-by-chunk using `write_direct_chunk()` or equivalent
   - Hash each chunk immediately after writing: `sha256(chunk_data.tobytes())`
   - Accumulate chunk hashes into the dataset hash
   - Optionally write the `_chunk_hashes` companion dataset
3. For each group:
   - Write all attributes (except `content_hash`)
   - Hash attributes as they are written
   - Accumulate into the group hash
4. Finalize the Merkle root: `content_hash = sha256(root_group_hash)`
5. Write the `content_hash` root attribute
6. Close the file (sealed, immutable)

**SDK API design:** The SDK enforces this pattern via a context-manager / builder API:

```python
with fd5.create(path, product="recon", ...) as f:
    f.write_volume(data)           # hashes computed inline
    f.write_metadata(metadata_dict)  # hashes accumulated
    # On context exit: Merkle root finalized, content_hash written, file sealed
```

There is no `fd5.open_for_edit()`. Files are immutable after creation (see Immutability and concurrency section).

**Full verification:** reopen, recompute chunk hashes from data, recompute Merkle tree, compare with stored `content_hash`.

**Fast verification:** reopen, recompute Merkle tree from stored `_chunk_hashes` tables (no data reads), compare with stored `content_hash`. This verifies the hash chain is intact but does not re-verify data against chunk hashes.

#### When to include chunk hashes

Per-chunk hashing is **optional**. The file-level `content_hash` is always required. Chunk hashes are recommended for:

- Large datasets (> 100 MB) where full re-hashing is expensive
- Products that may be accessed over high-latency storage (network mounts, future cloud access)
- Long-term archival where partial corruption detection is valuable

Small datasets (metadata groups, MIPs, small calibration tables) do not benefit from chunk hashing -- the overhead of the companion dataset exceeds the verification benefit.

### Required vs. optional fields

**Required root attrs (ALL product types, ALL domains):**

| Attr | Required | Notes |
|---|---|---|
| `_schema_version` | Yes | fd5 core schema version |
| `product` | Yes | Product type string (domain-defined) |
| `id` | Yes | Algorithm-prefixed SHA-256 of identity inputs |
| `id_inputs` | Yes | Documents what was hashed |
| `name` | Yes | Human-readable name |
| `description` | Yes | Natural-language description (AI-readability) |
| `content_hash` | Yes | Algorithm-prefixed Merkle root (integrity) |
| `timestamp` | Conditional | Required for measured/acquired data; absent for simulations and synthetic products |
| `domain` | No | Scientific domain string (recommended) |
| `default` | No | Path to best visualization dataset (strongly recommended) |

**Required per product type (medical imaging domain):**

| Product | Required groups/datasets | Optional |
|---|---|---|
| `recon` | `volume`, `metadata/`, `provenance/` | `pyramid/`, `mip_coronal`, `mip_sagittal`, `mips_per_frame/`, `frames/` (required if 4D+), `sources/`, `extra/` |
| `listmode` | At least one of `raw_data/` or `proc_data/`, `metadata/`, `provenance/` | `sources/`, `extra/` |
| `sinogram` | `sinogram` (dataset), `metadata/`, `provenance/` | Correction datasets, `sources/`, `extra/` |
| `sim` | `metadata/simulation/`, `provenance/` | `events/`, `ground_truth/`, `sources/`, `extra/` |
| `transform` | `metadata/method/`, at least one of `matrix` or `displacement_field`, `sources/` (source + target) | `inverse_*`, `landmarks/`, `extra/` |
| `calibration` | `metadata/calibration/`, `data/` (at least one dataset), `provenance/` | `sources/`, `extra/` |
| `spectrum` | `counts` (dataset), `axes/` (at least `ax0/`), `metadata/method/` | `counts_errors`, `fit/`, `sources/`, `extra/` |
| `roi` | At least one of `mask`, `geometry/`, `contours/`; `regions/` (at least one); `metadata/method/` | `statistics/`, `sources/`, `extra/` |

Other domains define their own required fields per product type, following the same pattern: at least one primary dataset, a `metadata/` group with `_type`/`_version`, and `provenance/`.

**Domain-specific source headers are provenance, not required data.** For example, a DICOM header lives in `provenance/dicom_header`, a FASTQ header in `provenance/fastq_header`. Only present when relevant. The fd5 core does not mandate any specific source header format.

**`sources/` is optional at the product level.** A raw acquisition or first-in-chain product has no sources. A derived product has sources (e.g., a reconstruction references its listmode input; a variant call set references its alignment). The `sources/` group is present when there are upstream dependencies, absent when there are none.

### `study/` and context groups in HDF5

**HDF5 is self-contained.** Every fd5 file carries study-level and context metadata so a single file can be understood in isolation.

The `study/` group is domain-agnostic and always present:

```
├── study/
│   attrs: {type: str,                 # domain-defined (e.g., "clinical", "research", "calibration", "synthetic")
│           license: "CC-BY-4.0",      # SPDX identifier (required for RO-Crate export)
│           description: "Study type and context"}
│   creators/                           # optional: RO-Crate author field
│       creator_0/
│           attrs: {name, affiliation, orcid, role, description}
```

Additional context groups are **domain-specific**. The fd5 core does not mandate a specific context group beyond `study/`, but each domain schema defines what is needed. For example:

**Medical imaging:**

```
├── subject/                            # patient/specimen demographics
│   attrs: {species, pseudonym, birth_date, sex, description}
├── phantom/                            # for calibration/QC studies
│   attrs: {model, description, ...}
```

**Genomics:**

```
├── sample/                             # biological sample
│   attrs: {sample_id, tissue, organism, strain, description}
├── library/                            # sequencing library preparation
│   attrs: {library_id, strategy, source, selection, description}
```

**Remote sensing:**

```
├── platform/                           # satellite/drone/ground station
│   attrs: {platform_id, sensor, orbit, description}
```

These context groups are **identical across all files in a dataset** (redundant by design). The manifest sections are the human-readable dump of the same data. If they conflict, the HDF5 is authoritative.
