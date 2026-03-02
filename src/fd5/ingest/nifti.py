"""fd5.ingest.nifti — NIfTI loader for fd5.

Reads NIfTI-1 / NIfTI-2 files (``.nii``, ``.nii.gz``) via *nibabel* and
produces sealed fd5 ``recon`` files using ``fd5.create()``.
"""

from __future__ import annotations

try:
    import nibabel as nib
except ImportError as exc:
    raise ImportError(
        "nibabel is required for NIfTI ingest. "
        "Install it with: pip install 'fd5[nifti]'"
    ) from exc

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from fd5._types import Fd5Path
from fd5.create import create
from fd5.ingest._base import hash_source_files

__all__ = ["NiftiLoader", "ingest_nifti"]

_INGEST_TOOL = "fd5.ingest.nifti"
_INGEST_VERSION = "0.1.0"


def _get_affine(img: nib.spatialimages.SpatialImage) -> np.ndarray:
    """Extract the best available affine (sform preferred, then qform)."""
    header = img.header
    if hasattr(header, "get_sform") and header["sform_code"] > 0:
        return header.get_sform().astype(np.float64)
    if hasattr(header, "get_qform") and header["qform_code"] > 0:
        return header.get_qform().astype(np.float64)
    return img.affine.astype(np.float64)


def _dimension_order(ndim: int) -> str:
    """Map array dimensionality to fd5 dimension_order string."""
    if ndim == 3:
        return "ZYX"
    if ndim == 4:
        return "TZYX"
    return "".join(["D"] * (ndim - 3)) + "ZYX"


def ingest_nifti(
    nifti_path: Path | str,
    output_dir: Path | str,
    *,
    product: str = "recon",
    name: str,
    description: str,
    timestamp: str | None = None,
    reference_frame: str = "RAS",
    study_metadata: dict[str, Any] | None = None,
) -> Fd5Path:
    """Read a NIfTI file and produce a sealed fd5 ``recon`` file.

    Parameters
    ----------
    nifti_path:
        Path to ``.nii`` or ``.nii.gz`` file.
    output_dir:
        Directory where the sealed fd5 file will be written.
    product:
        fd5 product type (default ``"recon"``).
    name:
        Human-readable name for the dataset.
    description:
        Description of the dataset.
    timestamp:
        ISO-8601 timestamp; auto-generated if *None*.
    reference_frame:
        Spatial reference frame (default ``"RAS"``).
    study_metadata:
        Optional dict with ``study_type``, ``license``, ``description``,
        and optionally ``creators`` for the study group.

    Returns
    -------
    Path to the sealed fd5 file.
    """
    nifti_path = Path(nifti_path)
    output_dir = Path(output_dir)

    if not nifti_path.exists():
        raise FileNotFoundError(f"NIfTI file not found: {nifti_path}")

    img = nib.load(nifti_path)
    volume = np.asarray(img.dataobj, dtype=np.float32)
    affine = _get_affine(img)
    dim_order = _dimension_order(volume.ndim)

    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc).isoformat()

    ingest_ts = datetime.now(tz=timezone.utc).isoformat()
    original_files = hash_source_files([nifti_path])

    existing = set(output_dir.glob("*.h5")) if output_dir.exists() else set()

    with create(
        output_dir,
        product=product,
        name=name,
        description=description,
        timestamp=timestamp,
    ) as builder:
        builder.file.attrs["scanner"] = "nifti-import"
        builder.file.attrs["vendor_series_id"] = str(nifti_path.name)

        builder.write_product(
            {
                "volume": volume,
                "affine": affine,
                "dimension_order": dim_order,
                "reference_frame": reference_frame,
                "description": description,
            }
        )

        builder.write_provenance(
            original_files=original_files,
            ingest_tool=_INGEST_TOOL,
            ingest_version=_INGEST_VERSION,
            ingest_timestamp=ingest_ts,
        )

        if study_metadata:
            builder.write_study(
                study_type=study_metadata["study_type"],
                license=study_metadata["license"],
                description=study_metadata.get("description", description),
                creators=study_metadata.get("creators"),
            )

    new_files = set(output_dir.glob("*.h5")) - existing
    return next(iter(new_files))


class NiftiLoader:
    """Loader implementation for NIfTI files."""

    @property
    def supported_product_types(self) -> list[str]:
        return ["recon"]

    def ingest(
        self,
        source: Path | str,
        output_dir: Path,
        *,
        product: str = "recon",
        name: str,
        description: str,
        timestamp: str | None = None,
        **kwargs: Any,
    ) -> Fd5Path:
        return ingest_nifti(
            source,
            output_dir,
            product=product,
            name=name,
            description=description,
            timestamp=timestamp,
            **kwargs,
        )
