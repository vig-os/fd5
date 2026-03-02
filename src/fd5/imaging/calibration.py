"""fd5.imaging.calibration — Calibration product schema for detector/scanner calibration.

Implements the ``calibration`` product schema per white-paper.md § calibration.
Handles normalization arrays, attenuation maps, detector efficiency tables,
timing offsets, crystal maps, and related calibration data with flexible
type-dependent dataset structure.
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np

_SCHEMA_VERSION = "1.0.0"

_GZIP_LEVEL = 4

_ID_INPUTS = ["calibration_type", "scanner_model", "scanner_serial", "valid_from"]

_CALIBRATION_TYPES = frozenset(
    {
        "energy_calibration",
        "gain_map",
        "normalization",
        "dead_time",
        "timing_calibration",
        "crystal_map",
        "sensitivity",
        "cross_calibration",
    }
)


class CalibrationSchema:
    """Product schema for detector / scanner calibration (``calibration``)."""

    product_type: str = "calibration"
    schema_version: str = _SCHEMA_VERSION

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "calibration"},
                "calibration_type": {
                    "type": "string",
                    "enum": sorted(_CALIBRATION_TYPES),
                },
                "scanner_model": {"type": "string"},
                "scanner_serial": {"type": "string"},
                "valid_from": {"type": "string"},
                "valid_until": {"type": "string"},
                "default": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "domain": {"type": "string"},
                "metadata": {
                    "type": "object",
                    "description": "Calibration metadata including type-specific parameters and conditions",
                },
                "data": {
                    "type": "object",
                    "description": "Calibration datasets — structure depends on calibration_type",
                },
            },
            "required": [
                "_schema_version",
                "product",
                "calibration_type",
                "scanner_model",
                "scanner_serial",
                "valid_from",
                "valid_until",
            ],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {
            "product": "calibration",
            "domain": "medical_imaging",
        }

    def id_inputs(self) -> list[str]:
        return list(_ID_INPUTS)

    def write(self, target: h5py.File | h5py.Group, data: dict[str, Any]) -> None:
        """Write calibration data to *target*.

        *data* must contain:
        - ``calibration_type``: str — one of the recognised calibration types
        - ``scanner_model``: str
        - ``scanner_serial``: str
        - ``valid_from``: str (ISO 8601)
        - ``valid_until``: str (ISO 8601 or ``"indefinite"``)

        Optional / type-dependent keys:
        - ``default``: str — path to primary calibration dataset
        - ``metadata``: dict with ``calibration`` and ``conditions`` sub-dicts
        - type-specific dataset dicts (e.g. ``channel_to_energy``, ``gain_map``)
        """
        target.attrs["calibration_type"] = data["calibration_type"]
        target.attrs["scanner_model"] = data["scanner_model"]
        target.attrs["scanner_serial"] = data["scanner_serial"]
        target.attrs["valid_from"] = data["valid_from"]
        target.attrs["valid_until"] = data["valid_until"]

        if "default" in data:
            target.attrs["default"] = data["default"]

        if "metadata" in data:
            self._write_metadata(target, data["metadata"])

        cal_type = data["calibration_type"]
        writer = _DATA_WRITERS.get(cal_type)
        if writer is not None:
            writer(self, target, data)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _write_metadata(
        self,
        target: h5py.File | h5py.Group,
        metadata: dict[str, Any],
    ) -> None:
        meta_grp = target.require_group("metadata")

        if "calibration" in metadata:
            cal_meta = metadata["calibration"]
            cal_grp = meta_grp.create_group("calibration")
            for key, value in cal_meta.items():
                if isinstance(value, dict):
                    sub = cal_grp.create_group(key)
                    for sk, sv in value.items():
                        sub.attrs[sk] = _coerce_attr(sv)
                elif isinstance(value, list):
                    cal_grp.attrs[key] = _coerce_list_attr(key, value)
                else:
                    cal_grp.attrs[key] = _coerce_attr(value)

        if "conditions" in metadata:
            cond = metadata["conditions"]
            cond_grp = meta_grp.create_group("conditions")
            if "description" in cond:
                cond_grp.attrs["description"] = cond["description"]
            for key, value in cond.items():
                if key == "description":
                    continue
                if isinstance(value, dict):
                    sub = cond_grp.create_group(key)
                    for sk, sv in value.items():
                        sub.attrs[sk] = _coerce_attr(sv)

    # ------------------------------------------------------------------
    # Data writers per calibration_type
    # ------------------------------------------------------------------

    def _write_energy_calibration(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        grp = target.require_group("data")

        if "channel_to_energy" in data:
            arr = np.asarray(data["channel_to_energy"], dtype=np.float64)
            ds = grp.create_dataset("channel_to_energy", data=arr)
            ds.attrs["units"] = "keV"
            ds.attrs["description"] = "Energy per channel"

        if "reference_spectrum" in data:
            arr = np.asarray(data["reference_spectrum"], dtype=np.float64)
            ds = grp.create_dataset("reference_spectrum", data=arr)
            ds.attrs["description"] = "Measured spectrum of calibration source"

    def _write_gain_map(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        grp = target.require_group("data")
        if "gain_map" in data:
            arr = np.asarray(data["gain_map"], dtype=np.float32)
            ds = grp.create_dataset(
                "gain_map",
                data=arr,
                compression="gzip",
                compression_opts=_GZIP_LEVEL,
            )
            ds.attrs["description"] = "Per-crystal gain correction factors"

    def _write_normalization(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        grp = target.require_group("data")

        if "norm_factors" in data:
            arr = np.asarray(data["norm_factors"], dtype=np.float32)
            ds = grp.create_dataset(
                "norm_factors",
                data=arr,
                compression="gzip",
                compression_opts=_GZIP_LEVEL,
            )
            ds.attrs["description"] = "Normalization correction factors"

        if "efficiency_map" in data:
            arr = np.asarray(data["efficiency_map"], dtype=np.float32)
            ds = grp.create_dataset(
                "efficiency_map",
                data=arr,
                compression="gzip",
                compression_opts=_GZIP_LEVEL,
            )
            ds.attrs["description"] = "Per-crystal detection efficiency"

    def _write_dead_time(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        grp = target.require_group("data")
        if "dead_time_curve" in data:
            arr = np.asarray(data["dead_time_curve"], dtype=np.float64)
            ds = grp.create_dataset("dead_time_curve", data=arr)
            ds.attrs["count_rate__units"] = "cps"
            ds.attrs["description"] = "Dead-time correction as function of count rate"

    def _write_timing_calibration(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        grp = target.require_group("data")

        if "timing_offsets" in data:
            arr = np.asarray(data["timing_offsets"], dtype=np.float32)
            ds = grp.create_dataset(
                "timing_offsets",
                data=arr,
                compression="gzip",
                compression_opts=_GZIP_LEVEL,
            )
            ds.attrs["units"] = "ns"
            ds.attrs["description"] = "Per-crystal timing offset corrections"

        if "resolution_curve" in data:
            arr = np.asarray(data["resolution_curve"], dtype=np.float64)
            ds = grp.create_dataset("resolution_curve", data=arr)
            ds.attrs["energy__units"] = "keV"
            ds.attrs["fwhm__units"] = "ns"
            ds.attrs["description"] = "Timing resolution as function of energy"

    def _write_crystal_map(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        grp = target.require_group("data")

        if "crystal_positions" in data:
            arr = np.asarray(data["crystal_positions"], dtype=np.float64)
            ds = grp.create_dataset("crystal_positions", data=arr)
            ds.attrs["description"] = "Crystal centre coordinates"

        if "crystal_ids" in data:
            arr = np.asarray(data["crystal_ids"], dtype=np.int64)
            ds = grp.create_dataset("crystal_ids", data=arr)
            ds.attrs["description"] = "Crystal identifier per element"

    def _write_sensitivity(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        grp = target.require_group("data")
        if "sensitivity_profile" in data:
            arr = np.asarray(data["sensitivity_profile"], dtype=np.float64)
            ds = grp.create_dataset("sensitivity_profile", data=arr)
            ds.attrs["description"] = "System sensitivity profile"

    def _write_cross_calibration(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        pass


_DATA_WRITERS: dict[str, Any] = {
    "energy_calibration": CalibrationSchema._write_energy_calibration,
    "gain_map": CalibrationSchema._write_gain_map,
    "normalization": CalibrationSchema._write_normalization,
    "dead_time": CalibrationSchema._write_dead_time,
    "timing_calibration": CalibrationSchema._write_timing_calibration,
    "crystal_map": CalibrationSchema._write_crystal_map,
    "sensitivity": CalibrationSchema._write_sensitivity,
    "cross_calibration": CalibrationSchema._write_cross_calibration,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_attr(value: Any) -> Any:
    """Coerce a Python value to an HDF5-compatible attribute type."""
    if isinstance(value, int) and not isinstance(value, bool):
        return np.int64(value)
    if isinstance(value, float):
        return np.float64(value)
    return value


def _coerce_list_attr(key: str, lst: list[Any]) -> Any:
    """Coerce a Python list to an HDF5-compatible attribute array."""
    if not lst:
        return np.array([], dtype=np.float64)
    first = lst[0]
    if isinstance(first, str):
        dt = h5py.special_dtype(vlen=str)
        return np.array(lst, dtype=dt)
    return np.asarray(lst)
