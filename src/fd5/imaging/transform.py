"""fd5.imaging.transform — Transform product schema for spatial registrations.

Implements the ``transform`` product schema per white-paper.md § transform.
Handles 4x4 affine matrices (rigid/affine), dense displacement fields
(deformable), transform type attributes, source/target reference frames,
and optional inverse transforms and landmark correspondences.
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np

_SCHEMA_VERSION = "1.0.0"

_GZIP_LEVEL = 4

_ID_INPUTS = ["timestamp", "source_image_id", "target_image_id"]

_VALID_TRANSFORM_TYPES = {"rigid", "affine", "deformable", "bspline"}
_VALID_DIRECTIONS = {"source_to_target", "target_to_source"}
_VALID_DEFAULTS = {"matrix", "displacement_field"}


class TransformSchema:
    """Product schema for spatial registrations (``transform``)."""

    product_type: str = "transform"
    schema_version: str = _SCHEMA_VERSION

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "transform"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "transform_type": {
                    "type": "string",
                    "enum": sorted(_VALID_TRANSFORM_TYPES),
                },
                "direction": {
                    "type": "string",
                    "enum": sorted(_VALID_DIRECTIONS),
                },
            },
            "required": [
                "_schema_version",
                "product",
                "name",
                "description",
                "transform_type",
                "direction",
            ],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {
            "product": "transform",
            "domain": "medical_imaging",
        }

    def id_inputs(self) -> list[str]:
        return list(_ID_INPUTS)

    def write(self, target: h5py.File | h5py.Group, data: dict[str, Any]) -> None:
        """Write transform data to *target*.

        *data* must contain:
        - ``transform_type``: str — one of "rigid", "affine", "deformable", "bspline"
        - ``direction``: str — "source_to_target" or "target_to_source"

        At least one of:
        - ``matrix``: float64 (4, 4) affine transformation matrix
        - ``displacement_field``: dict with "data", "affine", "reference_frame",
          "component_order"

        Optional keys:
        - ``inverse_matrix``: float64 (4, 4)
        - ``inverse_displacement_field``: dict (same structure as displacement_field)
        - ``metadata``: dict with "method" and/or "quality" sub-dicts
        - ``landmarks``: dict with "source_points", "target_points", optional "labels"
        """
        transform_type = data["transform_type"]
        if transform_type not in _VALID_TRANSFORM_TYPES:
            msg = f"Invalid transform_type {transform_type!r}"
            raise ValueError(msg)

        direction = data["direction"]
        if direction not in _VALID_DIRECTIONS:
            msg = f"Invalid direction {direction!r}"
            raise ValueError(msg)

        target.attrs["transform_type"] = transform_type
        target.attrs["direction"] = direction

        has_matrix = "matrix" in data
        has_field = "displacement_field" in data

        if has_matrix:
            target.attrs["default"] = "matrix"
        elif has_field:
            target.attrs["default"] = "displacement_field"

        if "default" in data:
            target.attrs["default"] = data["default"]

        if has_matrix:
            self._write_matrix(target, data["matrix"])

        if has_field:
            self._write_displacement_field(target, data["displacement_field"])

        if "inverse_matrix" in data:
            self._write_inverse_matrix(target, data["inverse_matrix"])

        if "inverse_displacement_field" in data:
            self._write_inverse_displacement_field(
                target, data["inverse_displacement_field"]
            )

        if "metadata" in data:
            self._write_metadata(target, data["metadata"])

        if "landmarks" in data:
            self._write_landmarks(target, data["landmarks"])

    # ------------------------------------------------------------------
    # Matrix
    # ------------------------------------------------------------------

    def _write_matrix(
        self,
        target: h5py.File | h5py.Group,
        matrix: np.ndarray,
    ) -> None:
        mat = np.asarray(matrix, dtype=np.float64)
        ds = target.create_dataset("matrix", data=mat)
        ds.attrs["description"] = (
            "4x4 affine transformation matrix (homogeneous coordinates)"
        )
        ds.attrs["convention"] = "LPS"
        ds.attrs["units"] = "mm"

    # ------------------------------------------------------------------
    # Displacement field
    # ------------------------------------------------------------------

    def _write_displacement_field(
        self,
        target: h5py.File | h5py.Group,
        field_data: dict[str, Any],
    ) -> None:
        arr = np.asarray(field_data["data"], dtype=np.float32)
        chunks = (1,) * (arr.ndim - 1) + (arr.shape[-1],)
        ds = target.create_dataset(
            "displacement_field",
            data=arr,
            chunks=chunks,
            compression="gzip",
            compression_opts=_GZIP_LEVEL,
        )
        ds.attrs["affine"] = np.asarray(field_data["affine"], dtype=np.float64)
        ds.attrs["reference_frame"] = field_data["reference_frame"]
        ds.attrs["component_order"] = field_data["component_order"]
        ds.attrs["description"] = "Dense displacement vector field in mm"

    # ------------------------------------------------------------------
    # Inverse matrix
    # ------------------------------------------------------------------

    def _write_inverse_matrix(
        self,
        target: h5py.File | h5py.Group,
        matrix: np.ndarray,
    ) -> None:
        mat = np.asarray(matrix, dtype=np.float64)
        ds = target.create_dataset("inverse_matrix", data=mat)
        ds.attrs["description"] = "Inverse transformation matrix"

    # ------------------------------------------------------------------
    # Inverse displacement field
    # ------------------------------------------------------------------

    def _write_inverse_displacement_field(
        self,
        target: h5py.File | h5py.Group,
        field_data: dict[str, Any],
    ) -> None:
        arr = np.asarray(field_data["data"], dtype=np.float32)
        chunks = (1,) * (arr.ndim - 1) + (arr.shape[-1],)
        ds = target.create_dataset(
            "inverse_displacement_field",
            data=arr,
            chunks=chunks,
            compression="gzip",
            compression_opts=_GZIP_LEVEL,
        )
        ds.attrs["description"] = (
            "Inverse displacement field (approximate for deformable)"
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _write_metadata(
        self,
        target: h5py.File | h5py.Group,
        metadata: dict[str, Any],
    ) -> None:
        grp = target.create_group("metadata")

        if "method" in metadata:
            self._write_method(grp, metadata["method"])

        if "quality" in metadata:
            self._write_quality(grp, metadata["quality"])

    def _write_method(
        self,
        parent: h5py.Group,
        method: dict[str, Any],
    ) -> None:
        grp = parent.create_group("method")
        grp.attrs["_type"] = method["_type"]
        grp.attrs["_version"] = np.int64(method.get("_version", 1))
        if "description" in method:
            grp.attrs["description"] = method["description"]
        if "optimizer" in method:
            grp.attrs["optimizer"] = method["optimizer"]
        if "metric" in method:
            grp.attrs["metric"] = method["metric"]
        if "n_iterations" in method:
            grp.attrs["n_iterations"] = np.int64(method["n_iterations"])
        if "convergence" in method:
            grp.attrs["convergence"] = np.float64(method["convergence"])
        if "regularization" in method:
            grp.attrs["regularization"] = method["regularization"]
        if "regularization_weight" in method:
            grp.attrs["regularization_weight"] = np.float64(
                method["regularization_weight"]
            )
        if "n_levels" in method:
            grp.attrs["n_levels"] = np.int64(method["n_levels"])
        if "n_landmarks" in method:
            grp.attrs["n_landmarks"] = np.int64(method["n_landmarks"])
        if "operator" in method:
            grp.attrs["operator"] = method["operator"]
        if "grid_spacing" in method:
            gs = method["grid_spacing"]
            gs_grp = grp.create_group("grid_spacing")
            gs_grp.attrs["value"] = np.array(gs["value"], dtype=np.float64)
            gs_grp.attrs["units"] = gs.get("units", "mm")
            gs_grp.attrs["unitSI"] = np.float64(gs.get("unitSI", 0.001))

    def _write_quality(
        self,
        parent: h5py.Group,
        quality: dict[str, Any],
    ) -> None:
        grp = parent.create_group("quality")
        grp.attrs["description"] = "Registration quality metrics"
        if "metric_value" in quality:
            grp.attrs["metric_value"] = np.float64(quality["metric_value"])
        if "jacobian_min" in quality:
            grp.attrs["jacobian_min"] = np.float64(quality["jacobian_min"])
        if "jacobian_max" in quality:
            grp.attrs["jacobian_max"] = np.float64(quality["jacobian_max"])

        if "tre" in quality:
            tre = quality["tre"]
            tre_grp = grp.create_group("tre")
            tre_grp.attrs["value"] = np.float64(tre["value"])
            tre_grp.attrs["units"] = tre.get("units", "mm")
            tre_grp.attrs["unitSI"] = np.float64(tre.get("unitSI", 0.001))

    # ------------------------------------------------------------------
    # Landmarks
    # ------------------------------------------------------------------

    def _write_landmarks(
        self,
        target: h5py.File | h5py.Group,
        landmarks: dict[str, Any],
    ) -> None:
        grp = target.create_group("landmarks")

        src = np.asarray(landmarks["source_points"], dtype=np.float64)
        ds_src = grp.create_dataset("source_points", data=src)
        ds_src.attrs["units"] = "mm"
        ds_src.attrs["description"] = "Landmark positions in source image space"

        tgt = np.asarray(landmarks["target_points"], dtype=np.float64)
        ds_tgt = grp.create_dataset("target_points", data=tgt)
        ds_tgt.attrs["units"] = "mm"
        ds_tgt.attrs["description"] = "Landmark positions in target image space"

        if "labels" in landmarks:
            labels = landmarks["labels"]
            dt = h5py.special_dtype(vlen=str)
            ds_lbl = grp.create_dataset("labels", data=labels, dtype=dt)
            ds_lbl.attrs["description"] = "Anatomical labels for each landmark pair"
