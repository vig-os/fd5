"""fd5.imaging.sinogram — Sinogram product schema for projection data.

Implements the ``sinogram`` product schema per white-paper.md § sinogram.
Handles 3D/4D float32 arrays indexed by detector coordinates
(radial, angular, axial ring-difference, optionally TOF bin) with
scanner geometry metadata and correction flags.
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np

_SCHEMA_VERSION = "1.0.0"

_GZIP_LEVEL = 4

_ID_INPUTS = ["timestamp", "scanner", "vendor_series_id"]


class SinogramSchema:
    """Product schema for projection data (``sinogram``)."""

    product_type: str = "sinogram"
    schema_version: str = _SCHEMA_VERSION

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "sinogram"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "domain": {"type": "string"},
                "n_radial": {"type": "integer"},
                "n_angular": {"type": "integer"},
                "n_planes": {"type": "integer"},
                "span": {"type": "integer"},
                "max_ring_diff": {"type": "integer"},
                "tof_bins": {"type": "integer"},
            },
            "required": [
                "_schema_version",
                "product",
                "name",
                "description",
                "n_radial",
                "n_angular",
                "n_planes",
                "span",
                "max_ring_diff",
                "tof_bins",
            ],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {
            "product": "sinogram",
            "domain": "medical_imaging",
        }

    def id_inputs(self) -> list[str]:
        return list(_ID_INPUTS)

    def write(self, target: h5py.File | h5py.Group, data: dict[str, Any]) -> None:
        """Write sinogram data to *target*.

        *data* must contain:
        - ``sinogram``: numpy float32 array, 3D (n_planes, n_angular, n_radial)
          or 4D (n_planes, n_tof, n_angular, n_radial) when TOF
        - ``n_radial``, ``n_angular``, ``n_planes``: int
        - ``span``: int — axial compression factor
        - ``max_ring_diff``: int
        - ``tof_bins``: int — 0 or 1 for non-TOF

        Optional keys:
        - ``acquisition``: dict with scanner geometry
        - ``corrections_applied``: dict with correction flags
        - ``additive_correction``: numpy array (same shape as sinogram)
        - ``multiplicative_correction``: numpy array (same shape as sinogram)
        """
        self._write_root_attrs(target, data)
        self._write_sinogram(target, data["sinogram"])
        self._write_metadata(target, data)

        if "additive_correction" in data:
            self._write_correction(
                target,
                "additive_correction",
                data["additive_correction"],
                "Additive correction term (scatter + randoms)",
            )

        if "multiplicative_correction" in data:
            self._write_correction(
                target,
                "multiplicative_correction",
                data["multiplicative_correction"],
                "Multiplicative correction term (normalization * attenuation)",
            )

    # ------------------------------------------------------------------
    # Root attrs
    # ------------------------------------------------------------------

    def _write_root_attrs(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        target.attrs["n_radial"] = np.int64(data["n_radial"])
        target.attrs["n_angular"] = np.int64(data["n_angular"])
        target.attrs["n_planes"] = np.int64(data["n_planes"])
        target.attrs["span"] = np.int64(data["span"])
        target.attrs["max_ring_diff"] = np.int64(data["max_ring_diff"])
        target.attrs["tof_bins"] = np.int64(data["tof_bins"])

    # ------------------------------------------------------------------
    # Sinogram dataset
    # ------------------------------------------------------------------

    def _write_sinogram(
        self,
        target: h5py.File | h5py.Group,
        sinogram: np.ndarray,
    ) -> None:
        ndim = sinogram.ndim
        chunks = (1,) * (ndim - 2) + sinogram.shape[-2:]
        ds = target.create_dataset(
            "sinogram",
            data=sinogram,
            chunks=chunks,
            compression="gzip",
            compression_opts=_GZIP_LEVEL,
        )
        ds.attrs["description"] = "Projection data in sinogram format"

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _write_metadata(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        meta = target.create_group("metadata")

        if "acquisition" in data:
            self._write_acquisition(meta, data["acquisition"])

        if "corrections_applied" in data:
            self._write_corrections_applied(meta, data["corrections_applied"])

    def _write_acquisition(
        self,
        meta_grp: h5py.Group,
        acq: dict[str, Any],
    ) -> None:
        grp = meta_grp.create_group("acquisition")
        grp.attrs["n_rings"] = np.int64(acq["n_rings"])
        grp.attrs["n_crystals_per_ring"] = np.int64(acq["n_crystals_per_ring"])
        grp.attrs["description"] = "Scanner geometry"

        rs_grp = grp.create_group("ring_spacing")
        rs_grp.attrs["value"] = np.float64(acq["ring_spacing"])
        rs_grp.attrs["units"] = "mm"
        rs_grp.attrs["unitSI"] = np.float64(0.001)

        cp_grp = grp.create_group("crystal_pitch")
        cp_grp.attrs["value"] = np.float64(acq["crystal_pitch"])
        cp_grp.attrs["units"] = "mm"
        cp_grp.attrs["unitSI"] = np.float64(0.001)

    def _write_corrections_applied(
        self,
        meta_grp: h5py.Group,
        corrections: dict[str, bool],
    ) -> None:
        grp = meta_grp.create_group("corrections_applied")
        grp.attrs["normalization"] = np.bool_(corrections.get("normalization", False))
        grp.attrs["attenuation"] = np.bool_(corrections.get("attenuation", False))
        grp.attrs["scatter"] = np.bool_(corrections.get("scatter", False))
        grp.attrs["randoms"] = np.bool_(corrections.get("randoms", False))
        grp.attrs["dead_time"] = np.bool_(corrections.get("dead_time", False))
        grp.attrs["decay"] = np.bool_(corrections.get("decay", False))
        grp.attrs["description"] = (
            "Which corrections have been applied to this sinogram"
        )

    # ------------------------------------------------------------------
    # Correction datasets
    # ------------------------------------------------------------------

    def _write_correction(
        self,
        target: h5py.File | h5py.Group,
        name: str,
        array: np.ndarray,
        description: str,
    ) -> None:
        ndim = array.ndim
        chunks = (1,) * (ndim - 2) + array.shape[-2:]
        ds = target.create_dataset(
            name,
            data=array,
            chunks=chunks,
            compression="gzip",
            compression_opts=_GZIP_LEVEL,
        )
        ds.attrs["description"] = description
