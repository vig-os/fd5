# fd5 -- FAIR Data on HDF5

## Abstract

`fd5` is a self-describing, FAIR-principled data format for scientific data products built on HDF5. It defines conventions for storing volumetric images, event-based data, simulation outputs, and arbitrary scientific measurements alongside their full metadata, provenance, and schema -- all inside a single HDF5 file per data product.

The HDF5 file is the **single source of truth**. Every other representation (TOML manifests, YAML metadata exports, datacite records) is a derived, human-readable dump that can be regenerated from the HDF5 at any time.

`fd5` is format-agnostic on the input side. It does not parse DICOMs, ROOT files, MIDAS streams, or vendor-specific scanner output. Those are upstream concerns handled by domain-specific ingest pipelines. `fd5` defines what the clean, canonical data product looks like once it exists.


## Motivation

### The problem

Scientific data -- especially in medical imaging, nuclear physics, and detector R&D -- typically starts as vendor-specific scanner output: DICOMs with thousands of inconsistent tags, proprietary listmode formats, INI configuration files, ad-hoc HDF5 layouts, and scattered metadata in spreadsheets and lab notebooks.

Working with this data involves:
- **Fragile caching layers** (JSON/pickle manifests that corrupt, go stale, or can't serialize domain types)
- **Repeated parsing overhead** (re-reading DICOM headers every time, re-computing derived quantities)
- **Scattered metadata** (acquisition parameters in DICOMs, bed positions in INI files, tracer info in separate TOML protocols, operator notes in emails)
- **No precomputed artifacts** (every visualization requires loading full volumes)
- **No machine-readable schema** (new collaborators, AI agents, and automated pipelines must reverse-engineer the data structure)
- **No provenance chain** (which raw data produced this reconstruction? which CT was used for attenuation correction?)

### The solution

Treat scanner output as archival "junk" -- keep it, hash it, link to it, but never work with it directly. Instead, ingest it once into a clean, self-describing format where:

1. One file = one data product (a reconstruction, a listmode acquisition, a simulation)
2. All metadata lives inside the file, structured as nested groups with attributes
3. The schema is embedded in the file itself, not in external documentation
4. Precomputed artifacts (projections, thumbnails) are stored alongside the data
5. Provenance links trace every product back to its sources
6. Any tool -- from `h5dump` to an LLM -- can understand the file without domain-specific code


## Design Principles

### 1. HDF5 is the single source of truth

The HDF5 file contains everything: data, metadata, schema, provenance, precomputed artifacts. All other representations are derived dumps. If the TOML manifest is deleted, regenerate it. If the datacite YAML is lost, regenerate it. The HDF5 file is canonical.

### 2. FAIR compliance (classic)

| Principle | Implementation |
|-----------|----------------|
| **Findable** | Persistent identifier (`id`) as root attribute. Rich, structured metadata. Human-readable filenames with timestamps. |
| **Accessible** | HDF5 is an open, standardized format supported by every scientific computing platform. No proprietary dependencies. |
| **Interoperable** | `@units` and `@unitSI` on every numerical field (NeXus/OpenPMD conventions). ISO 8601 timestamps with timezone. Standard vocabulary references for modalities and anatomy. |
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

A single acquisition (e.g., a whole-body PET scan) may produce multiple data products with fundamentally different structures:

| Product type | Data structure | Typical size | Access pattern |
|-------------|---------------|-------------|----------------|
| `recon` | 3D/4D voxel grid | 100 MB -- 1 GB | Slice reads, MIP preview |
| `listmode` | Event tables (compound datasets) | 100 MB -- 10 GB | Sequential scan, time windowing |
| `sinogram` | 3D projection array | 100 MB -- 1 GB | Full read |
| `sim` | Event tables + ground truth volumes | Variable | Analysis-specific |
| `transform` | 4x4 matrix or displacement field | 1 KB -- 1 GB | Resampling, ROI propagation |
| `calibration` | Gain maps, curves, lookup tables | 1 KB -- 100 MB | Referenced by recon/listmode |
| `spectrum` | ND histograms with bin edges + fits | 1 KB -- 100 MB | Full read, fitting, visualization |
| `roi` | Label masks, contours, geometric shapes | 1 KB -- 100 MB | Region lookup, statistics |

Each gets its own file. This keeps files manageable, allows independent access, and matches the natural unit of scientific work ("I want the Q.Clear reconstruction" not "I want byte range 4.2--5.1 GB of the monolithic scan file").

### 5. Groups are nested dicts

HDF5 groups with attributes provide native nested-dictionary storage. No JSON serialization, no custom encoders, no corruption from interrupted writes to text files. The helpers `h5_to_dict(group) -> dict` and `dict_to_h5(group, d)` provide round-trip conversion. Any HDF5 viewer can browse the structure.

### 6. `_type` + `_version` for forward-compatible extensibility

Any group that could have multiple implementations carries:
- `_type` (str): what kind of thing this is (e.g., `"q_clear"`, `"osem"`, `"dlir"`, `"gate"`)
- `_version` (int): which generation of that type's schema

A new reconstruction algorithm, correction method, or simulation code just uses a new `_type` value with its own attributes. **No schema change. No re-ingest of existing data.** Old readers encountering an unknown `_type` gracefully skip or display just the type string. `_version` handles breaking changes within a type; readers log warnings for unknown versions but still read what they can.

### 7. `@units` + `@unitSI` on every numerical field

Inspired by NeXus and OpenPMD:
- `units` (str): human-readable unit string (`"mm"`, `"s"`, `"MBq"`, `"keV"`)
- `unitSI` (float): numeric conversion factor to SI base units (`0.001` for mm, `1.0` for s, `1e6` for MBq)

Field names are bare (`z_min`, `duration`, `activity`) -- they do not embed units. This prevents the `z_min_mm` vs `z_min_m` vs `z_min_cm` naming chaos and enables automated unit conversion: `value_si = value * unitSI`.

### 8. Additive-only schema evolution

New schema versions only add attributes and groups. They never remove or rename existing ones. A v2 reader can always read a v1 file. A v1 reader encountering v2 data reads what it knows and ignores the rest.

### 9. Embedded schema definition

The root of every `fd5` file carries a `_schema` attribute containing a JSON Schema document describing the file's structure. This is not for validation during normal use (though it can be) -- it's for **self-description**. An AI agent or unfamiliar tool reads `_schema` and knows exactly what groups and attributes to expect, their types, and their semantics.

### 10. ISO 8601 with explicit timezone

All timestamps include timezone offset: `"2024-07-24T18:14:00+02:00"`. No ambiguity when files move between institutions, time zones, or continents. Midnight in Vienna is not midnight in Boston.

### 11. Provenance as a DAG, not a string

A PET reconstruction depends on listmode data AND a CT for attenuation correction. A simulation reconstruction depends on simulated events AND a ground truth phantom definition. These relationships form a directed acyclic graph (DAG), stored in a `sources/` group with HDF5 external links to the source products. Each source also stores the source file's content hash for integrity verification.

Provenance lives in metadata, not in filenames. Filenames describe identity ("what is this"); metadata describes relationships ("where did it come from").

### 12. Two hashes, two purposes

Every `fd5` file carries two distinct hashes:

- **`id`** (root attr): SHA-256 of identity inputs (`product + vendor + vendor_id + timestamp`), prefixed with algorithm: `"sha256:a1b2c3..."`. This is the **persistent identity** -- stable across re-ingests, schema upgrades, and recompression. The companion `id_inputs` attr documents exactly what was hashed. Filenames use the first 8 hex chars for brevity.
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


## File Naming Convention

```
YYYY-MM-DD_HH-MM-SS_<product>-<id>_<descriptors>.h5
```

- **Datetime prefix**: acquisition timestamp for chronological `ls` sorting
- **Product type**: `recon`, `listmode`, `sinogram`, `sim`, `transform`, `calibration`, `spectrum`, `roi`
- **ID**: first 8 hex chars of the full SHA-256 identity hash (for filename brevity)
- **Descriptors**: freeform, human-readable labels separated by underscores (modality, method, body region, etc.)

Examples:
```
2024-07-24_18-14-00_recon-87f032f6_ct_thorax_dlir.h5
2024-07-24_19-06-10_recon-2a3ac438_pet_qclear_wb.h5
2024-07-24_19-06-10_listmode-def67890_pet_coinc.h5
2024-07-24_19-23-16_listmode-abc12345_pet_singles_bed1.h5
2024-07-24_19-30-00_spectrum-44556677_pet_lifetime_pals.h5
2024-07-24_19-06-10_spectrum-88990011_pet_energy_coinc_matrix.h5
2024-07-24_19-06-10_roi-aabb1122_pet_tumor_contours.h5
2024-07-24_19-06-10_roi-ccdd3344_pet_organs_totalseg.h5
roi-eeff5566_phantom_nema_spheres.h5
sim-xyz99999_pet_nema_gate.h5
```

Simulations lack acquisition timestamps and omit the datetime prefix.

The filename is **convenience, not identity**. The `<id>` in the filename is the first 8 hex characters of the full `id` hash (e.g., `sha256:2a3ac438e7f1...` becomes `2a3ac438` in the filename). The real identity is the full `id` attribute inside the HDF5 file. Renaming a file breaks nothing. The `fd5` package sets file `mtime` to the acquisition timestamp during creation, so file managers sort chronologically even without parsing the name.

Descriptors are freeform -- not BIDS-style `key-value` pairs. They exist for `ls` and `grep`, not for machine parsing. Machine-readable metadata lives inside the HDF5.


## HDF5 Schema

### Root attributes (common to all products)

Every `fd5` file carries these attributes on the root group, plus the `study/`, `subject/` (or `phantom/`) groups for self-containment:

| Attribute | Type | Description |
|-----------|------|-------------|
| `_schema` | str (JSON) | JSON Schema document describing this file's structure |
| `_schema_version` | int | fd5 schema version (monotonically increasing) |
| `product` | str | Product type: `"recon"`, `"listmode"`, `"sinogram"`, `"sim"`, `"transform"`, `"calibration"`, `"spectrum"`, `"roi"` |
| `id` | str | Persistent unique identifier, algorithm-prefixed SHA-256 of identity inputs (e.g., `"sha256:a1b2c3d4..."`) |
| `id_inputs` | str | Documents what was hashed to produce `id` (e.g., `"product + vendor + vendor_id + timestamp"`) |
| `name` | str | Human-readable name |
| `description` | str | Natural-language description of this data product |
| `scan_type` | str | Modality: `"ct"`, `"pet"`, `"mri"` |
| `scan_type_vocabulary` | str | Vocabulary system, e.g. `"DICOM Modality (0008,0060)"` (optional) |
| `scan_type_code` | str | Standard code in that vocabulary, e.g. `"PT"`, `"CT"` (optional) |
| `vendor` | str | Scanner vendor (optional for non-scanner products) |
| `vendor_id` | str | Vendor-assigned series/acquisition ID (optional for non-scanner products) |
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

### Units convention

Every attribute or dataset with physical meaning carries two companion attributes:

```
z_min = -450.2
z_min__units = "mm"
z_min__unitSI = 0.001
```

The double-underscore `__units` / `__unitSI` suffix convention avoids collisions with HDF5 attribute namespaces and makes units unambiguously associated with their parent field. (When the field is a dataset rather than an attribute, `units` and `unitSI` are attributes on the dataset itself, following the NeXus convention.)

### Vocabulary references

Domain-specific string fields (modalities, anatomical regions, procedure types) carry optional vocabulary attributes:

```
scan_type = "pet"
scan_type_vocabulary = "DICOM Modality"
scan_type_code = "PT"
```

These use **human-readable standard names** -- not hex tag IDs or obscure numeric codes. The vocabulary name itself is enough for lookup. Common vocabularies:
- **DICOM Modality** for imaging modalities (`CT`, `PT`, `MR`, `NM`)
- **SNOMED CT** for anatomical regions (by name, not by numeric code)
- **RadLex** for imaging procedures and findings

Vocabulary attributes are optional and additive. Their absence doesn't break anything.

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
                injection_activity: 350.0, injection_activity__units: "MBq",
                half_life: 6586.2, half_life__units: "s",
                description: "Radiotracer administration details"}
    acquisition/
        attrs: {n_beds: 4, mode: "3D",
                frame_durations: [120.0, 120.0, 120.0, 120.0],
                frame_durations__units: "s",
                description: "Data acquisition parameters"}
    reconstruction/
        attrs: {_type: "q_clear", _version: 1,
                beta: 350, iterations: 25, tof: true, psf: true,
                description: "Penalized-likelihood reconstruction (GE Q.Clear)"}
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
        attrs: {kvp: 120, kvp__units: "kV",
                mas: 250, mas__units: "mAs",
                pitch: 0.984,
                rotation_time: 0.5, rotation_time__units: "s",
                description: "CT acquisition parameters"}
    reconstruction/
        attrs: {_type: "dlir", _version: 1,
                strength: "medium", kernel: "STANDARD",
                description: "Deep learning image reconstruction"}
    dose/
        attrs: {ctdi_vol: 12.5, ctdi_vol__units: "mGy",
                dlp: 450.0, dlp__units: "mGy*cm",
                description: "Radiation dose metrics"}
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

The external links provide transparent HDF5 access to source data (when available). The `content_hash` enables integrity verification even if the source file has moved. The `role` attribute documents the semantic relationship.

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
    notes/
        attrs: {operator: "Dr. Smith",
                comment: "Patient moved during bed position 3",
                description: "Operator notes recorded during acquisition"}
```

### Reserved conventions

| Convention | Meaning | Status |
|------------|---------|--------|
| `_type` | Polymorphic type identifier on a group | Active |
| `_version` | Schema version for a `_type` | Active |
| `_schema` | Embedded JSON Schema (root only) | Active |
| `_schema_version` | fd5 format version (root only) | Active |
| `__units` | Unit string suffix on an attribute | Active |
| `__unitSI` | SI conversion factor suffix on an attribute | Active |
| `_errors` | Uncertainty dataset with same shape as parent | Active (used in `spectrum/counts_errors`) |
| `_vocabulary` | Vocabulary system name suffix | Active |
| `_code` | Standard code suffix in named vocabulary | Active |
| `description` | Natural-language description on any group/dataset | Active |
| `default` | Path to recommended visualization target | Active |
| `id` | Algorithm-prefixed SHA-256 of identity inputs (root only) | Active |
| `id_inputs` | Documents what was hashed to produce `id` (root only) | Active |
| `content_hash` | Algorithm-prefixed SHA-256 of file content at write time | Active |


## Product Schemas

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
├── attrs: (common) + {z_min, z_max, duration, n_slices}
│
├── metadata/                       # structured acquisition + reconstruction params
│   # (see detailed PET/CT metadata examples in the metadata section above)
│
├── volume                          # dataset: float32, shape depends on dimensionality
│   attrs: {
│       affine: float64[4,4],       # spatial affine (always 3D: maps voxel to mm)
│       reference_frame: str,
│       voxel_size__units: "mm",
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
│           attrs: {sampling_rate__units: "Hz",
│                   description: "Raw physiological gating signal"}
│       trigger_times               # dataset: float64 (N_triggers,)
│           attrs: {units: "s", description: "Detected trigger timestamps"}
│
├── pyramid/                        # multiscale resolution pyramid (inspired by OME-Zarr NGFF)
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
│               voxel_size__units: "mm",
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
│           z_extent__units: "mm", x_extent__units: "mm",
│           description: "Coronal MIP (summed over all frames if dynamic)"}
├── mip_sagittal                    # float32, (Z, Y)
│   attrs: {projection_type: "mip", axis: 2,
│           z_extent__units: "mm", y_extent__units: "mm",
│           description: "Sagittal MIP (summed over all frames if dynamic)"}
│
├── mips_per_frame/                 # optional: per-frame MIPs for dynamic data
│   coronal                         # float32, (T, Z, X) -- one MIP per frame
│       attrs: {projection_type: "mip", axis: 1, description: "Per-frame coronal MIPs"}
│   sagittal                        # float32, (T, Z, Y)
│       attrs: {projection_type: "mip", axis: 2, description: "Per-frame sagittal MIPs"}
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

**Multiscale pyramid** (inspired by OME-Zarr NGFF):

The `pyramid/` group stores successively downsampled copies of the full-resolution `volume`, enabling progressive-resolution access without loading the entire dataset. This is the same core idea behind OME-Zarr's multiscale image pyramids, adapted to HDF5's single-file model.

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
│       attrs: {n_rings, n_crystals_per_ring, ring_spacing__units: "mm",
│               crystal_pitch__units: "mm", description: "Scanner geometry"}
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
│   │           grid_spacing: [4.0, 4.0, 4.0], grid_spacing__units: "mm",
│   │           n_levels: 3}
│   │
│   │   # --- _type: "manual_landmark" ---
│   │   attrs: {n_landmarks: 12, operator: "Dr. Smith"}
│   │
│   quality/
│       attrs: {metric_value: float,    # final metric value
│               tre: float, tre__units: "mm",   # target registration error (if landmarks available)
│               jacobian_min: float,    # minimum Jacobian determinant (deformable only)
│               jacobian_max: float,    # negative = folding
│               description: "Registration quality metrics"}
│
├── matrix                              # dataset: float64 (4, 4) -- for rigid/affine
│   attrs: {description: "4x4 affine transformation matrix (homogeneous coordinates)",
│           convention: "LPS" | "RAS",
│           units: "mm"}
│
├── displacement_field                  # dataset: float32 (Z, Y, X, 3) -- for deformable
│   attrs: {affine: float64[4,4],       # defines the grid in physical space
│           reference_frame: str,
│           voxel_size__units: "mm",
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
│   │           n_crystals_axial: 36, n_crystals_transaxial: 672,
│   │           acquisition_duration: 14400.0, acquisition_duration__units: "s"}
│   │
│   │   # --- _type: "cross_calibration" ---
│   │   attrs: {reference_instrument: "dose_calibrator",
│   │           reference_model: "Capintec CRC-55tR",
│   │           calibration_factor: 1.023, calibration_factor_error: 0.008,
│   │           phantom: "uniform_cylinder",
│   │           activity: 45.0, activity__units: "MBq"}
│   │
│   conditions/
│       attrs: {temperature: 22.0, temperature__units: "degC",
│               humidity: 45.0, humidity__units: "%",
│               description: "Environmental conditions during calibration"}
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
│   │   attrs: {time_resolution: 0.180, time_resolution__units: "ns",
│   │           start_signal: "22Na 1274 keV",
│   │           stop_signal: "annihilation 511 keV",
│   │           source_activity: 25.0, source_activity__units: "kBq"}
│   │
│   │   # --- _type: "energy" ---
│   │   attrs: {detector: "HPGe", energy_range: [0, 1500],
│   │           energy_range__units: "keV", live_time: 3600.0,
│   │           live_time__units: "s"}
│   │
│   │   # --- _type: "doppler" ---
│   │   attrs: {line_energy: 511.0, line_energy__units: "keV",
│   │           s_parameter: 0.487, w_parameter: 0.012}
│   │
│   │   # --- _type: "coincidence_matrix" ---
│   │   attrs: {detector_1: "HPGe_left", detector_2: "HPGe_right",
│   │           coincidence_window: 10.0, coincidence_window__units: "ns"}
│   │
│   │   # --- _type: "angular" (ACAR) ---
│   │   attrs: {geometry: "1D" | "2D",
│   │           angular_range: [-30, 30], angular_range__units: "mrad"}
│   │
│   acquisition/
│       attrs: {total_counts: int, live_time__units: "s", real_time__units: "s",
│               dead_time_fraction: float,
│               description: "Acquisition statistics"}
│
├── counts                              # dataset: the histogram itself
│   │                                   # 1D: shape (N_bins,)
│   │                                   # 2D: shape (N_bins_ax0, N_bins_ax1)
│   │                                   # ND: shape (N_bins_ax0, ..., N_bins_axN)
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
│                   lifetime: 0.382, lifetime__units: "ns",
│                   lifetime_error: 0.005, lifetime_error__units: "ns",
│                   intensity: 0.72, intensity_error: 0.02,
│                   description: "Free positron annihilation component"}
│           curve                       # dataset: this component's contribution
│       component_1/
│           attrs: {label: "positronium",
│                   lifetime: 1.85, lifetime__units: "ns",
│                   intensity: 0.28,
│                   description: "Ortho-positronium component"}
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
│           voxel_size__units: "mm",
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
│           attrs: {volume: float, volume__units: "mL",
│                   mean: float, mean__units: "...",
│                   max: float, max__units: "...",
│                   std: float, std__units: "...",
│                   n_voxels: int,
│                   computed_on: str,   # id of image used for statistics
│                   description: "ROI statistics"}
│
├── geometry/                           # alternative/complement to mask: parametric shapes
│   <shape_name>/
│       attrs: {shape: "sphere" | "cylinder" | "box" | "ellipsoid",
│               center: [x, y, z], center__units: "mm",
│               # shape-specific:
│               radius: float, radius__units: "mm",        # sphere
│               dimensions: [w, h, d], dimensions__units: "mm",  # box
│               label_value: int,
│               description: str}
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

### Schema dump

The embedded `_schema` attribute can be extracted to a standalone JSON Schema file for documentation or validation tooling:

```bash
fd5 schema-dump data/2024-07-24_19-06-10_recon-2a3ac438_pet_qclear_wb.h5 > schema.json
```


## Scope and Non-Goals

`fd5` defines **what a clean data product looks like**. It does not define how to get there.

**In scope:**
- HDF5 schema conventions and attribute patterns
- Reading and writing `fd5`-compliant HDF5 files
- TOML manifest generation and parsing
- Datacite metadata generation
- Content hashing and integrity verification
- Schema embedding and validation
- `h5_to_dict` / `dict_to_h5` helpers
- Filename generation

**Out of scope (handled by domain-specific packages):**
- DICOM parsing and grouping
- Vendor-specific scanner output formats
- Listmode data processing
- Image reconstruction
- Ingest pipeline orchestration
- Dataset discovery from raw scanner directories

The boundary is clean: the ingest pipeline (in a separate package) produces `fd5` files. From that point forward, `fd5` handles everything.


## Comparison with Existing Formats

| Format | Strengths | Gaps that fd5 addresses |
|--------|-----------|------------------------|
| **NeXus/HDF5** | Mature, `@units`, `default` chain, `NXcollection` | Tied to neutron/X-ray domain; no per-product files; complex class hierarchy |
| **OpenPMD** | `unitSI`, mesh/particle duality | Focused on particle-in-cell simulations; no medical imaging conventions |
| **BIDS** | Self-describing filenames, metadata inheritance, sidecar JSON | Tied to neuroimaging (MRI/EEG); no PET listmode; filenames encode too much |
| **NIfTI** | Simple, widely supported for volumes | No metadata beyond affine; no provenance; no non-volume data |
| **DICOM RT-STRUCT** | Clinical standard for contours, integrated with treatment planning | Contour-only (no masks), tied to DICOM ecosystem, no AI model provenance, no geometric VOIs |
| **DICOM** | Comprehensive tags, universal in clinical imaging | Verbose, inconsistent across vendors, poor for non-image data, no precomputed artifacts |
| **ROOT/TTree** | Excellent for event data, schema evolution | C++ ecosystem; poor Python ergonomics; no self-describing metadata conventions |
| **Zarr v3** | Cloud-native chunked storage, parallel I/O, per-chunk independence | Storage engine only; no metadata conventions, no provenance, no schema embedding |
| **OME-Zarr (NGFF)** | Multiscale pyramids, cloud-optimized bioimaging, growing tool ecosystem | Microscopy-focused; no event data, spectra, or calibration; no embedded schema; no provenance DAG; no per-product identity |

`fd5` takes the best ideas from each:
- `@units` + `@unitSI` from NeXus and OpenPMD
- `default` attribute chain from NeXus
- `extra/` unvalidated collection from NeXus (`NXcollection`)
- Human-readable filenames inspired by BIDS (but freeform, not key-value)
- `_type`/`_version` extensibility inspired by NeXus `NXentry` typing and ROOT schema evolution
- ISO 8601 with timezone from NeXus best practices
- `_errors` suffix convention from NeXus
- Multiscale resolution pyramids inspired by OME-Zarr NGFF (adapted to HDF5's single-file model)
- Per-chunk content hashing inspired by Zarr's per-chunk integrity model (rolled up into a Merkle tree)
- Content hashing from scientific reproducibility best practices


## FAIR Compliance Summary

| FAIR Principle | fd5 Feature |
|----------------|-------------|
| **F1**: Globally unique identifier | `id` -- algorithm-prefixed SHA-256 of identity inputs, stable across re-ingests |
| **F2**: Rich metadata | `metadata/` group tree, `description` on every group/dataset |
| **F3**: Metadata includes identifier | `id` is a root attribute in every file |
| **F4**: Registered in searchable resource | `manifest.toml` as local index; `datacite.yml` for catalog registration |
| **A1**: Retrievable by identifier | Direct file access; manifest maps id to file path |
| **A1.1**: Open, free protocol | HDF5 = open standard; h5py = open source |
| **A2**: Metadata accessible even if data unavailable | Manifest contains all metadata; `h5dump -A` extracts attrs without data |
| **I1**: Formal, shared knowledge representation | JSON Schema embedded; `@units`/`@unitSI`; vocabulary references |
| **I2**: FAIR vocabularies | DICOM Modality codes, SNOMED CT, RadLex (human-readable, not hex) |
| **I3**: Qualified references | `sources/` with typed roles (`emission`, `attenuation`, `mu_map`) |
| **R1**: Rich, plurality of attributes | Three metadata layers: flat root attrs, structured `metadata/` groups, raw DICOM header in `provenance/` |
| **R1.1**: Clear usage license | License field in datacite metadata |
| **R1.2**: Detailed provenance | `sources/` DAG + `provenance/original_files` with SHA-256 hashes |
| **R1.3**: Meet domain standards | NeXus/OpenPMD conventions; DICOM vocabulary references |

### AI-Readability

| Capability | fd5 Feature |
|------------|-------------|
| Schema discovery | `_schema` root attribute (JSON Schema) |
| Content understanding | `description` on every group and dataset |
| Unit interpretation | `__units` (string) + `__unitSI` (numeric factor) |
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

**Reserved attr prefixes:** Attrs starting with `_` (`_type`, `_version`, `_schema`, `_schema_version`) are included in the dict. The `__units` and `__unitSI` suffixed attrs are included as-is (the caller handles pairing them with their parent field).

### `id` computation

The `id` is a SHA-256 hash of identity inputs, prefixed with `"sha256:"`. The identity inputs depend on the product type:

| Product type | Identity inputs | Rationale |
|---|---|---|
| `recon` | `timestamp + scanner_uuid + vendor_series_id` | Same acquisition on same scanner = same identity |
| `listmode` | `timestamp + scanner_uuid + vendor_series_id` | Same as recon |
| `sinogram` | `timestamp + scanner_uuid + vendor_series_id` | Same as recon |
| `sim` | `simulation_config_hash + random_seed` | Same config + seed = same simulation |
| `transform` | `source_id + target_id + method_type + creation_timestamp` | Same inputs + method = same transform |
| `calibration` | `scanner_uuid + calibration_type + valid_from` | Same scanner + type + time = same calibration |
| `spectrum` | `source_id + method_type + creation_timestamp` | Derived from specific data + method |
| `roi` | `reference_image_id + method_type + creation_timestamp` | Drawn on specific image at specific time |

**Serialization format:** concatenate the input fields with `\0` (null byte) separator, encode as UTF-8, compute SHA-256. The `id_inputs` attr stores a human-readable description: `"timestamp + scanner_uuid + vendor_series_id"`.

**`scanner_uuid`:** a stable identifier for the scanner instance. For GE scanners this is `StationName` + `DeviceSerialNumber` from DICOM. For simulations, absent. For manually created products (ROIs), absent -- use creation timestamp + method instead.

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

1. Write the entire file (all datasets, all attrs, all groups) **except** `content_hash` and `_chunk_hashes`
2. Close and reopen in `"r+"` mode (ensures all data is flushed)
3. For each chunked dataset: compute per-chunk hashes, write the `_chunk_hashes` companion dataset
4. Compute the Merkle tree (using chunk hashes for dataset hashes, skipping `_chunk_hashes` datasets)
5. Write the `content_hash` root attr
6. Close

**Full verification:** reopen, recompute chunk hashes from data, recompute Merkle tree, compare with stored `content_hash`.

**Fast verification:** reopen, recompute Merkle tree from stored `_chunk_hashes` tables (no data reads), compare with stored `content_hash`. This verifies the hash chain is intact but does not re-verify data against chunk hashes.

#### When to include chunk hashes

Per-chunk hashing is **optional**. The file-level `content_hash` is always required. Chunk hashes are recommended for:

- Large datasets (> 100 MB) where full re-hashing is expensive
- Products that may be accessed over high-latency storage (network mounts, future cloud access)
- Long-term archival where partial corruption detection is valuable

Small datasets (metadata groups, MIPs, small calibration tables) do not benefit from chunk hashing -- the overhead of the companion dataset exceeds the verification benefit.

### Required vs. optional fields

**Required root attrs (ALL product types):**

| Attr | Required | Notes |
|---|---|---|
| `_schema_version` | Yes | |
| `product` | Yes | |
| `id` | Yes | |
| `id_inputs` | Yes | |
| `name` | Yes | |
| `description` | Yes | AI-readability |
| `content_hash` | Yes | Integrity |
| `timestamp` | Conditional | Required for measured data; absent for simulations |
| `default` | No | But strongly recommended |

**Required per product type:**

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

**`dicom_header` is provenance, not required data.** It lives in `provenance/dicom_header` (not at the top level). Only present when the product was ingested from DICOM source files. Simulations, manual ROIs, and non-DICOM sources will not have it.

**`sources/` is optional at the product level.** A raw acquisition (first in the chain) has no sources. A reconstruction has sources (listmode + CTAC). The `sources/` group is present when there are upstream dependencies, absent when there are none.

### `study/` and `subject/` groups in HDF5

**HDF5 is self-contained.** Every fd5 file carries study and subject metadata so a single file can be understood in isolation.

```
├── study/
│   attrs: {type: "clinical",          # "clinical" | "preclinical" | "phantom" | "calibration"
│           description: "Study type and context"}
│
├── subject/                            # absent for phantom/calibration studies
│   attrs: {species: "human",          # "human" | "canine" | "porcine" | ...
│           pseudonym: "a3f2...",       # de-identified identifier
│           birth_date: "1959-03-15",  # ISO 8601 -- age is derived, birth_date is truth
│           weight: 72.0, weight__units: "kg",
│           sex: "M",                  # "M" | "F" | "O"
│           # species-specific (optional):
│           breed: "Beagle",           # canine, porcine, etc.
│           description: "Study subject demographics"}
│
├── phantom/                            # only for phantom/calibration studies
│   attrs: {model: "NEMA IEC",
│           known_activities: [10.0, 5.0, 2.5, 1.25],
│           known_activities__units: "MBq",
│           sphere_diameters: [37, 28, 22, 17],
│           sphere_diameters__units: "mm",
│           description: "Phantom specification"}
```

These groups are **identical across all files in a dataset** (redundant by design). The manifest `[subject]`/`[study]` sections are the human-readable dump of the same data. If they conflict, the HDF5 is authoritative.
