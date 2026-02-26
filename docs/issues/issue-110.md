---
type: issue
state: open
created: 2026-02-25T20:24:45Z
updated: 2026-02-25T21:06:03Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/110
comments: 0
labels: feature, effort:large, area:imaging
assignees: gerchowl
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:51.309Z
---

# [Issue 110]: [[FEATURE] fd5.ingest.dicom — DICOM series loader](https://github.com/vig-os/fd5/issues/110)

## Parent

Epic: #108 (Phase 6: Ingest Layer)

## Summary

Implement `src/fd5/ingest/dicom.py` — a loader that reads DICOM series (directories of `.dcm` files) and produces sealed fd5 files via `fd5.create()`.

## Scope

### Product types supported

| Product type | DICOM input | Notes |
|-------------|-------------|-------|
| `recon` | CT/PET/MR reconstructed image series | Volume + affine from ImagePositionPatient/PixelSpacing |
| `listmode` | PET listmode files (vendor-specific) | Stretch goal — vendor formats vary widely |

### Key functionality

1. **Series discovery** — group DICOM files by SeriesInstanceUID
2. **Volume assembly** — sort slices by ImagePositionPatient, stack into 3D/4D numpy array
3. **Affine computation** — derive affine matrix from DICOM geometry tags (ImagePositionPatient, ImageOrientationPatient, PixelSpacing, SliceThickness)
4. **Metadata extraction** — map DICOM tags to fd5 metadata attrs (scanner, timestamp, description, study info)
5. **Provenance** — record all source DICOM files with SHA-256 hashes in `provenance/original_files`
6. **De-identification** — strip patient-identifying DICOM tags before embedding any DICOM header in provenance

### Dependency

```toml
[project.optional-dependencies]
dicom = ["pydicom>=2.4"]
```

The module must raise `ImportError` with a helpful message if `pydicom` is not installed.

## Proposed API

```python
def ingest_dicom(
    dicom_dir: Path,
    output_dir: Path,
    *,
    product: str = "recon",
    name: str,
    description: str,
    timestamp: str | None = None,  # extracted from DICOM if None
    study_metadata: dict | None = None,
    deidentify: bool = True,
) -> Path:
    """Read a DICOM series directory and produce a sealed fd5 file."""
```

## Acceptance criteria

- [ ] Implements `Loader` protocol from `fd5.ingest._base`
- [ ] Produces valid fd5 files that pass `fd5 validate`
- [ ] Affine matrix correctly derived from DICOM geometry tags
- [ ] Provenance records all source `.dcm` files with SHA-256 hashes
- [ ] Patient-identifying tags stripped when `deidentify=True`
- [ ] `ImportError` with clear message when pydicom not installed
- [ ] Tests with synthetic DICOM data (no real patient data in repo)
- [ ] ≥ 90% coverage

## Dependencies

Depends on: `fd5.ingest._base` (#109)
