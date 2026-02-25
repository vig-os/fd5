"""fd5.imaging.recon — Recon product schema for reconstructed image volumes.

Implements the ``recon`` product schema per white-paper.md § recon.
Handles 3D/4D/5D float32 volumes with multiscale pyramids, MIP projections,
dynamic frames, affine transforms, and chunked gzip compression.
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np

_SCHEMA_VERSION = "1.0.0"

_GZIP_LEVEL = 4

_ID_INPUTS = ["timestamp", "scanner", "vendor_series_id"]


class ReconSchema:
    """Product schema for reconstructed image volumes (``recon``)."""

    product_type: str = "recon"
    schema_version: str = _SCHEMA_VERSION

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "recon"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "domain": {"type": "string"},
                "volume": {
                    "type": "object",
                    "description": "Root-level volume dataset (represented as attrs in h5_to_dict)",
                },
            },
            "required": ["_schema_version", "product", "name", "description"],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {
            "product": "recon",
            "domain": "medical_imaging",
        }

    def id_inputs(self) -> list[str]:
        return list(_ID_INPUTS)

    def write(self, target: h5py.File | h5py.Group, data: dict[str, Any]) -> None:
        """Write recon data to *target*.

        *data* must contain:
        - ``volume``: numpy float32 array (3D, 4D, or 5D)
        - ``affine``: float64 (4, 4) spatial affine matrix
        - ``dimension_order``: str (e.g. ``"ZYX"``, ``"TZYX"``)
        - ``reference_frame``: str (e.g. ``"LPS"``)
        - ``description``: str describing the volume

        Optional keys:
        - ``frames``: dict with frame timing for 4D+ data
        - ``pyramid``: dict with ``scale_factors`` and ``method``
        """
        volume = data["volume"]
        self._write_volume(target, volume, data)

        spatial_vol = _spatial_volume(volume, data["dimension_order"])

        if "frames" in data:
            self._write_frames(target, data["frames"])

        if "pyramid" in data:
            self._write_pyramid(target, spatial_vol, data)

        self._write_mips(target, spatial_vol)

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------

    def _write_volume(
        self,
        target: h5py.File | h5py.Group,
        volume: np.ndarray,
        data: dict[str, Any],
    ) -> None:
        ndim = volume.ndim
        chunks = (1,) * (ndim - 2) + volume.shape[-2:]
        ds = target.create_dataset(
            "volume",
            data=volume,
            chunks=chunks,
            compression="gzip",
            compression_opts=_GZIP_LEVEL,
        )
        ds.attrs["affine"] = data["affine"]
        ds.attrs["dimension_order"] = data["dimension_order"]
        ds.attrs["reference_frame"] = data["reference_frame"]
        ds.attrs["description"] = data["description"]

    # ------------------------------------------------------------------
    # Frames (4D+ data)
    # ------------------------------------------------------------------

    def _write_frames(
        self,
        target: h5py.File | h5py.Group,
        frames: dict[str, Any],
    ) -> None:
        grp = target.create_group("frames")
        grp.attrs["n_frames"] = np.int64(frames["n_frames"])
        grp.attrs["frame_type"] = frames["frame_type"]
        grp.attrs["description"] = frames["description"]

        grp.create_dataset(
            "frame_start",
            data=np.asarray(frames["frame_start"], dtype=np.float64),
        )
        grp["frame_start"].attrs["units"] = "s"
        grp["frame_start"].attrs["unitSI"] = np.float64(1.0)
        grp["frame_start"].attrs["description"] = (
            "Start time of each frame relative to reference"
        )

        grp.create_dataset(
            "frame_duration",
            data=np.asarray(frames["frame_duration"], dtype=np.float64),
        )
        grp["frame_duration"].attrs["units"] = "s"
        grp["frame_duration"].attrs["unitSI"] = np.float64(1.0)
        grp["frame_duration"].attrs["description"] = (
            "Duration of each frame (non-uniform allowed)"
        )

        if "frame_label" in frames:
            labels = frames["frame_label"]
            dt = h5py.special_dtype(vlen=str)
            grp.create_dataset("frame_label", data=labels, dtype=dt)
            grp["frame_label"].attrs["description"] = "Human-readable label per frame"

    # ------------------------------------------------------------------
    # Pyramid
    # ------------------------------------------------------------------

    def _write_pyramid(
        self,
        target: h5py.File | h5py.Group,
        spatial_vol: np.ndarray,
        data: dict[str, Any],
    ) -> None:
        pyramid_cfg = data["pyramid"]
        scale_factors = pyramid_cfg["scale_factors"]
        method = pyramid_cfg["method"]

        grp = target.create_group("pyramid")
        grp.attrs["n_levels"] = np.int64(len(scale_factors))
        grp.attrs["scale_factors"] = np.array(scale_factors, dtype=np.int64)
        grp.attrs["method"] = method
        grp.attrs["description"] = (
            "Multiscale pyramid for progressive-resolution access"
        )

        affine = data["affine"]

        for i, factor in enumerate(scale_factors, start=1):
            level_vol = _downsample(spatial_vol, factor)
            level_affine = _scale_affine(affine, factor)

            level_grp = grp.create_group(f"level_{i}")
            chunks = (1,) + level_vol.shape[1:]
            ds = level_grp.create_dataset(
                "volume",
                data=level_vol,
                chunks=chunks,
                compression="gzip",
                compression_opts=_GZIP_LEVEL,
            )
            ds.attrs["affine"] = level_affine
            ds.attrs["scale_factor"] = np.int64(factor)
            ds.attrs["description"] = f"{factor}x downsampled volume"

    # ------------------------------------------------------------------
    # MIP projections
    # ------------------------------------------------------------------

    def _write_mips(
        self,
        target: h5py.File | h5py.Group,
        spatial_vol: np.ndarray,
    ) -> None:
        # Coronal: project along Y (axis=1) → shape (Z, X)
        mip_cor = spatial_vol.max(axis=1).astype(np.float32)
        ds_cor = target.create_dataset("mip_coronal", data=mip_cor)
        ds_cor.attrs["projection_type"] = "mip"
        ds_cor.attrs["axis"] = np.int64(1)
        ds_cor.attrs["description"] = "Coronal MIP (summed over all frames if dynamic)"

        # Sagittal: project along X (axis=2) → shape (Z, Y)
        mip_sag = spatial_vol.max(axis=2).astype(np.float32)
        ds_sag = target.create_dataset("mip_sagittal", data=mip_sag)
        ds_sag.attrs["projection_type"] = "mip"
        ds_sag.attrs["axis"] = np.int64(2)
        ds_sag.attrs["description"] = "Sagittal MIP (summed over all frames if dynamic)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spatial_volume(volume: np.ndarray, dimension_order: str) -> np.ndarray:
    """Extract or derive the 3D spatial volume for MIP / pyramid computation.

    For 4D+ data, sum over all leading (non-spatial) dimensions.
    """
    n_spatial = 3  # Z, Y, X
    n_leading = volume.ndim - n_spatial
    result = volume
    for _ in range(n_leading):
        result = result.sum(axis=0)
    return result.astype(np.float32)


def _downsample(vol: np.ndarray, factor: int) -> np.ndarray:
    """Downsample a 3D volume by *factor* using stride-based subsampling."""
    return vol[::factor, ::factor, ::factor].copy()


def _scale_affine(affine: np.ndarray, factor: int) -> np.ndarray:
    """Scale the spatial part of an affine matrix by *factor*."""
    scaled = affine.copy()
    scaled[:3, :3] *= factor
    return scaled
