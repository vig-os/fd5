"""fd5.imaging.roi — ROI product schema for regions of interest.

Implements the ``roi`` product schema per white-paper.md § roi.
Handles label masks, parametric geometry, per-slice contours, region
metadata with optional statistics, and method provenance.
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np

_SCHEMA_VERSION = "1.0.0"

_GZIP_LEVEL = 4

_ID_INPUTS = ["timestamp", "scanner", "vendor_series_id"]


class RoiSchema:
    """Product schema for regions of interest (``roi``)."""

    product_type: str = "roi"
    schema_version: str = _SCHEMA_VERSION

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "roi"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "domain": {"type": "string"},
                "timestamp": {"type": "string"},
            },
            "required": ["_schema_version", "product", "name", "description"],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {
            "product": "roi",
            "domain": "medical_imaging",
        }

    def id_inputs(self) -> list[str]:
        return list(_ID_INPUTS)

    def write(self, target: h5py.File | h5py.Group, data: dict[str, Any]) -> None:
        """Write ROI data to *target*.

        *data* must contain at least one of:
        - ``mask``: dict with ``data`` (integer ndarray), ``affine``,
          ``reference_frame``, ``description``
        - ``geometry``: dict mapping shape names to shape definitions
        - ``contours``: dict with ``description`` and per-slice vertex data

        Optional keys:
        - ``metadata``: dict with ``method`` sub-dict (``_type``, ``_version``, ...)
        - ``regions``: dict mapping region names to region metadata
        - ``sources``: dict with ``reference_image`` sub-dict
        """
        if "metadata" in data:
            self._write_metadata(target, data["metadata"])

        if "mask" in data:
            self._write_mask(target, data["mask"])

        if "regions" in data:
            self._write_regions(target, data["regions"])

        if "geometry" in data:
            self._write_geometry(target, data["geometry"])

        if "contours" in data:
            self._write_contours(target, data["contours"])

        if "sources" in data:
            self._write_sources(target, data["sources"])

    # ------------------------------------------------------------------
    # Metadata / method
    # ------------------------------------------------------------------

    def _write_metadata(
        self,
        target: h5py.File | h5py.Group,
        metadata: dict[str, Any],
    ) -> None:
        meta_grp = target.create_group("metadata")
        if "method" in metadata:
            method = metadata["method"]
            method_grp = meta_grp.create_group("method")
            for key, val in method.items():
                method_grp.attrs[key] = val

    # ------------------------------------------------------------------
    # Mask
    # ------------------------------------------------------------------

    def _write_mask(
        self,
        target: h5py.File | h5py.Group,
        mask: dict[str, Any],
    ) -> None:
        arr = np.asarray(mask["data"])
        chunks = (1,) * (arr.ndim - 2) + arr.shape[-2:] if arr.ndim >= 3 else None
        ds = target.create_dataset(
            "mask",
            data=arr,
            chunks=chunks,
            compression="gzip",
            compression_opts=_GZIP_LEVEL,
        )
        ds.attrs["affine"] = np.asarray(mask["affine"], dtype=np.float64)
        ds.attrs["reference_frame"] = mask["reference_frame"]
        ds.attrs["description"] = mask.get(
            "description",
            "Label mask where each integer maps to a named region",
        )

    # ------------------------------------------------------------------
    # Regions
    # ------------------------------------------------------------------

    def _write_regions(
        self,
        target: h5py.File | h5py.Group,
        regions: dict[str, Any],
    ) -> None:
        grp = target.create_group("regions")
        for name, region in regions.items():
            reg_grp = grp.create_group(name)
            reg_grp.attrs["label_value"] = np.int64(region["label_value"])
            reg_grp.attrs["color"] = np.array(region["color"], dtype=np.int64)
            reg_grp.attrs["description"] = region["description"]

            for opt in ("anatomy", "anatomy_vocabulary", "anatomy_code"):
                if opt in region:
                    reg_grp.attrs[opt] = region[opt]

            if "statistics" in region:
                self._write_statistics(reg_grp, region["statistics"])

    def _write_statistics(
        self,
        region_grp: h5py.Group,
        stats: dict[str, Any],
    ) -> None:
        stat_grp = region_grp.create_group("statistics")
        stat_grp.attrs["n_voxels"] = np.int64(stats["n_voxels"])
        stat_grp.attrs["computed_on"] = stats["computed_on"]
        stat_grp.attrs["description"] = stats.get("description", "ROI statistics")

        for measure in ("volume", "mean", "max", "std"):
            if measure in stats:
                m = stats[measure]
                m_grp = stat_grp.create_group(measure)
                m_grp.attrs["value"] = np.float64(m["value"])
                m_grp.attrs["units"] = m["units"]
                m_grp.attrs["unitSI"] = np.float64(m["unitSI"])

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _write_geometry(
        self,
        target: h5py.File | h5py.Group,
        geometry: dict[str, Any],
    ) -> None:
        grp = target.create_group("geometry")
        for name, shape_def in geometry.items():
            shape_grp = grp.create_group(name)
            shape_grp.attrs["shape"] = shape_def["shape"]
            shape_grp.attrs["label_value"] = np.int64(shape_def["label_value"])
            shape_grp.attrs["description"] = shape_def["description"]

            center_grp = shape_grp.create_group("center")
            center_grp.attrs["value"] = np.array(
                shape_def["center"],
                dtype=np.float64,
            )
            center_grp.attrs["units"] = "mm"
            center_grp.attrs["unitSI"] = np.float64(0.001)

            if shape_def["shape"] == "sphere" and "radius" in shape_def:
                r_grp = shape_grp.create_group("radius")
                r_grp.attrs["value"] = np.float64(shape_def["radius"])
                r_grp.attrs["units"] = "mm"
                r_grp.attrs["unitSI"] = np.float64(0.001)

            if shape_def["shape"] == "box" and "dimensions" in shape_def:
                d_grp = shape_grp.create_group("dimensions")
                d_grp.attrs["value"] = np.array(
                    shape_def["dimensions"],
                    dtype=np.float64,
                )
                d_grp.attrs["units"] = "mm"
                d_grp.attrs["unitSI"] = np.float64(0.001)

    # ------------------------------------------------------------------
    # Contours
    # ------------------------------------------------------------------

    def _write_contours(
        self,
        target: h5py.File | h5py.Group,
        contours: dict[str, Any],
    ) -> None:
        grp = target.create_group("contours")
        grp.attrs["description"] = contours.get(
            "description",
            "Per-slice contour coordinates (RT-STRUCT compatible)",
        )
        for slice_key, regions in contours.items():
            if slice_key == "description":
                continue
            slice_grp = grp.create_group(slice_key)
            for region_name, region_data in regions.items():
                vertices = np.asarray(region_data["vertices"], dtype=np.float32)
                ds = slice_grp.create_dataset(region_name, data=vertices)
                ds.attrs["units"] = "mm"
                ds.attrs["label_value"] = np.int64(region_data["label_value"])

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def _write_sources(
        self,
        target: h5py.File | h5py.Group,
        sources: dict[str, Any],
    ) -> None:
        grp = target.create_group("sources")
        if "reference_image" in sources:
            ref = sources["reference_image"]
            ref_grp = grp.create_group("reference_image")
            ref_grp.attrs["id"] = ref["id"]
            ref_grp.attrs["product"] = ref.get("product", "recon")
            ref_grp.attrs["role"] = "reference_image"
            ref_grp.attrs["description"] = ref.get(
                "description",
                "Image on which these ROIs were defined",
            )
            if "file" in ref:
                ref_grp.attrs["file"] = ref["file"]
            if "content_hash" in ref:
                ref_grp.attrs["content_hash"] = ref["content_hash"]
