"""fd5.ingest.dicom — DICOM series loader.

Reads DICOM series directories and produces sealed fd5 files via ``fd5.create()``.
Requires ``pydicom>=2.4`` — install with ``pip install fd5[dicom]``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from fd5._types import Fd5Path
from fd5.ingest._base import hash_source_files

try:
    import pydicom
except ImportError as exc:
    raise ImportError(
        "pydicom is required for DICOM ingest. Install it with: pip install fd5[dicom]"
    ) from exc

import fd5

_PATIENT_TAGS = frozenset(
    {
        "PatientName",
        "PatientID",
        "PatientBirthDate",
        "PatientBirthTime",
        "PatientSex",
        "PatientAge",
        "PatientWeight",
        "PatientAddress",
        "PatientTelephoneNumbers",
        "OtherPatientIDs",
        "OtherPatientNames",
        "EthnicGroup",
        "PatientComments",
        "ReferringPhysicianName",
        "InstitutionName",
        "InstitutionAddress",
        "InstitutionalDepartmentName",
    }
)


# ---------------------------------------------------------------------------
# Series discovery
# ---------------------------------------------------------------------------


def _discover_series(dicom_dir: Path) -> dict[str, list[Path]]:
    """Group DICOM files by SeriesInstanceUID.

    Non-DICOM files are silently skipped.
    """
    series: dict[str, list[Path]] = defaultdict(list)
    for p in sorted(dicom_dir.iterdir()):
        if not p.is_file():
            continue
        try:
            ds = pydicom.dcmread(str(p), stop_before_pixels=True, force=False)
        except Exception:
            continue
        uid = getattr(ds, "SeriesInstanceUID", None)
        if uid is not None:
            series[str(uid)].append(p)
    return dict(series)


# ---------------------------------------------------------------------------
# Volume assembly
# ---------------------------------------------------------------------------


def _sort_slices(dcm_files: list[Path]) -> list[pydicom.Dataset]:
    """Read DICOM files and sort by ImagePositionPatient z-coordinate."""
    datasets = [pydicom.dcmread(str(p)) for p in dcm_files]
    datasets.sort(key=lambda ds: float(ds.ImagePositionPatient[2]))
    return datasets


def _assemble_volume(datasets: list[pydicom.Dataset]) -> np.ndarray:
    """Stack sorted DICOM slices into a 3D float32 volume.

    Applies RescaleSlope/RescaleIntercept if present.
    """
    slices = []
    for ds in datasets:
        arr = ds.pixel_array.astype(np.float32)
        slope = float(getattr(ds, "RescaleSlope", 1.0))
        intercept = float(getattr(ds, "RescaleIntercept", 0.0))
        arr = arr * slope + intercept
        slices.append(arr)
    return np.stack(slices, axis=0)


# ---------------------------------------------------------------------------
# Affine computation
# ---------------------------------------------------------------------------


def _compute_affine(datasets: list[pydicom.Dataset]) -> np.ndarray:
    """Derive a 4×4 affine matrix from DICOM geometry tags.

    Uses ImagePositionPatient, ImageOrientationPatient, and PixelSpacing
    from the first slice plus the z-spacing derived from the first two slices
    (or SliceThickness as fallback for single-slice volumes).
    """
    ds0 = datasets[0]
    ipp = [float(v) for v in ds0.ImagePositionPatient]
    iop = [float(v) for v in ds0.ImageOrientationPatient]
    ps = [float(v) for v in ds0.PixelSpacing]

    row_cosines = np.array(iop[:3])
    col_cosines = np.array(iop[3:])

    if len(datasets) > 1:
        ipp1 = [float(v) for v in datasets[1].ImagePositionPatient]
        slice_vec = np.array(ipp1) - np.array(ipp)
        slice_spacing = np.linalg.norm(slice_vec)
        if slice_spacing > 0:
            slice_dir = slice_vec / slice_spacing
        else:
            slice_dir = np.cross(row_cosines, col_cosines)
            slice_spacing = float(getattr(ds0, "SliceThickness", 1.0))
    else:
        slice_dir = np.cross(row_cosines, col_cosines)
        slice_spacing = float(getattr(ds0, "SliceThickness", 1.0))

    affine = np.eye(4, dtype=np.float64)
    affine[:3, 0] = row_cosines * ps[1]
    affine[:3, 1] = col_cosines * ps[0]
    affine[:3, 2] = slice_dir * slice_spacing
    affine[:3, 3] = ipp
    return affine


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------


def _extract_timestamp(ds: pydicom.Dataset) -> str:
    """Extract an ISO 8601 timestamp from DICOM study/acquisition tags."""
    date_str = getattr(ds, "StudyDate", None) or getattr(ds, "AcquisitionDate", "")
    time_str = getattr(ds, "StudyTime", None) or getattr(ds, "AcquisitionTime", "")
    if not date_str or len(date_str) < 8:
        return datetime.now(tz=timezone.utc).isoformat()

    dt_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    if time_str:
        hh = time_str[:2]
        mm = time_str[2:4]
        ss = time_str[4:6] if len(time_str) >= 6 else "00"
        dt_str += f"T{hh}:{mm}:{ss}"
    return dt_str


def _extract_scanner(ds: pydicom.Dataset) -> str:
    """Build a scanner identifier from DICOM header tags."""
    parts = [
        getattr(ds, "Manufacturer", ""),
        getattr(ds, "StationName", ""),
    ]
    return " ".join(p for p in parts if p).strip() or "unknown"


# ---------------------------------------------------------------------------
# De-identification
# ---------------------------------------------------------------------------


def _deidentify(ds: pydicom.Dataset) -> dict[str, Any]:
    """Convert DICOM dataset to a JSON-safe dict with patient tags removed."""
    result: dict[str, Any] = {}
    for elem in ds:
        if elem.keyword in _PATIENT_TAGS:
            continue
        if elem.keyword == "PixelData":
            continue
        try:
            val = elem.value
            if isinstance(val, pydicom.Sequence):
                continue
            if isinstance(val, (pydicom.uid.UID, pydicom.valuerep.PersonName)):
                val = str(val)
            if isinstance(val, bytes):
                continue
            if isinstance(val, pydicom.multival.MultiValue):
                val = [float(v) if isinstance(v, (float, int)) else str(v) for v in val]
            json.dumps(val)
            result[elem.keyword] = val
        except (TypeError, ValueError):
            result[elem.keyword] = str(val)
    return result


def _ds_to_json_dict(ds: pydicom.Dataset) -> dict[str, Any]:
    """Convert DICOM dataset to a JSON-safe dict, preserving patient tags."""
    result: dict[str, Any] = {}
    for elem in ds:
        if elem.keyword == "PixelData":
            continue
        try:
            val = elem.value
            if isinstance(val, pydicom.Sequence):
                continue
            if isinstance(val, (pydicom.uid.UID, pydicom.valuerep.PersonName)):
                val = str(val)
            if isinstance(val, bytes):
                continue
            if isinstance(val, pydicom.multival.MultiValue):
                val = [float(v) if isinstance(v, (float, int)) else str(v) for v in val]
            json.dumps(val)
            result[elem.keyword] = val
        except (TypeError, ValueError):
            result[elem.keyword] = str(val)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingest_dicom(
    dicom_dir: Path,
    output_dir: Path,
    *,
    product: str = "recon",
    name: str,
    description: str,
    timestamp: str | None = None,
    study_metadata: dict | None = None,
    deidentify: bool = True,
) -> Path:
    """Read a DICOM series directory and produce a sealed fd5 file."""
    dicom_dir = Path(dicom_dir)
    output_dir = Path(output_dir)

    all_series = _discover_series(dicom_dir)
    if not all_series:
        raise ValueError(f"No DICOM series found in {dicom_dir}")

    series_uid = next(iter(all_series))
    dcm_files = all_series[series_uid]

    datasets = _sort_slices(dcm_files)
    volume = _assemble_volume(datasets)
    affine = _compute_affine(datasets)

    ref_ds = datasets[0]
    ts = timestamp or _extract_timestamp(ref_ds)
    scanner = _extract_scanner(ref_ds)

    file_records = hash_source_files(dcm_files)

    if deidentify:
        header_dict = _deidentify(ref_ds)
    else:
        header_dict = _ds_to_json_dict(ref_ds)

    with fd5.create(
        output_dir,
        product=product,
        name=name,
        description=description,
        timestamp=ts,
    ) as builder:
        builder.file.attrs["scanner"] = scanner
        builder.file.attrs["vendor_series_id"] = str(series_uid)

        builder.write_product(
            {
                "volume": volume,
                "affine": affine,
                "dimension_order": "ZYX",
                "reference_frame": "LPS",
                "description": description,
                "provenance": {
                    "dicom_header": json.dumps(header_dict),
                },
            }
        )

        builder.write_provenance(
            original_files=file_records,
            ingest_tool="fd5.ingest.dicom",
            ingest_version=fd5.__version__,
            ingest_timestamp=ts,
        )

    result_files = sorted(output_dir.glob("*.h5"))
    return result_files[-1]


class DicomLoader:
    """Loader that reads DICOM series and produces fd5 files."""

    @property
    def supported_product_types(self) -> list[str]:
        return ["recon"]

    def ingest(
        self,
        source: Path | str,
        output_dir: Path,
        *,
        product: str,
        name: str,
        description: str,
        timestamp: str | None = None,
        **kwargs,
    ) -> Fd5Path:
        if product not in self.supported_product_types:
            raise ValueError(
                f"Unsupported product type {product!r}. "
                f"Supported: {self.supported_product_types}"
            )
        return ingest_dicom(
            Path(source),
            Path(output_dir),
            product=product,
            name=name,
            description=description,
            timestamp=timestamp,
            **kwargs,
        )
