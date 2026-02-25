"""fd5.imaging.listmode — Listmode product schema for event-based detector data.

Implements the ``listmode`` product schema per white-paper.md § listmode.
Handles compound datasets for singles/coincidences/time_markers, mode attr,
table_pos, duration, z_min, z_max, and metadata/daq/ group.
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np

_SCHEMA_VERSION = "1.0.0"

_GZIP_LEVEL = 4

_ID_INPUTS = ["timestamp", "scanner", "vendor_series_id"]

_RAW_DATA_DATASETS = ("singles", "time_markers", "coin_counters", "table_positions")
_PROC_DATA_DATASETS = ("events_2p", "events_3p", "coin_2p", "coin_3p")


class ListmodeSchema:
    """Product schema for event-based detector data (``listmode``)."""

    product_type: str = "listmode"
    schema_version: str = _SCHEMA_VERSION

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "listmode"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "domain": {"type": "string"},
                "mode": {"type": "string"},
                "table_pos": {"type": "number"},
                "duration": {"type": "number"},
                "z_min": {"type": "number"},
                "z_max": {"type": "number"},
                "metadata": {
                    "type": "object",
                    "properties": {
                        "daq": {
                            "type": "object",
                            "description": "Data acquisition system parameters",
                        },
                    },
                },
                "raw_data": {
                    "type": "object",
                    "description": "Raw detector event datasets (compound)",
                },
                "proc_data": {
                    "type": "object",
                    "description": "Processed event datasets (compound)",
                },
            },
            "required": ["_schema_version", "product", "name", "description"],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {
            "product": "listmode",
            "domain": "medical_imaging",
        }

    def id_inputs(self) -> list[str]:
        return list(_ID_INPUTS)

    def write(self, target: h5py.File | h5py.Group, data: dict[str, Any]) -> None:
        """Write listmode data to *target*.

        *data* must contain:
        - ``mode``: str acquisition mode (e.g. ``"3d"``, ``"2d"``)
        - ``table_pos``: float table position in mm
        - ``duration``: float acquisition duration in seconds
        - ``z_min``: float axial field-of-view minimum in mm
        - ``z_max``: float axial field-of-view maximum in mm

        At least one of ``raw_data`` or ``proc_data`` must be present.

        - ``raw_data``: dict mapping dataset names to structured numpy arrays
        - ``proc_data``: dict mapping dataset names to structured numpy arrays

        Optional:
        - ``daq``: dict of DAQ parameters written to ``metadata/daq/``
        """
        self._write_root_attrs(target, data)

        if "raw_data" in data:
            self._write_event_group(target, "raw_data", data["raw_data"])

        if "proc_data" in data:
            self._write_event_group(target, "proc_data", data["proc_data"])

        if "daq" in data:
            self._write_daq(target, data["daq"])

    # ------------------------------------------------------------------
    # Root attributes
    # ------------------------------------------------------------------

    @staticmethod
    def _write_root_attrs(
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        target.attrs["mode"] = data["mode"]
        target.attrs["table_pos"] = np.float64(data["table_pos"])
        target.attrs["duration"] = np.float64(data["duration"])
        target.attrs["z_min"] = np.float64(data["z_min"])
        target.attrs["z_max"] = np.float64(data["z_max"])

    # ------------------------------------------------------------------
    # Event data groups (raw_data / proc_data)
    # ------------------------------------------------------------------

    @staticmethod
    def _write_event_group(
        target: h5py.File | h5py.Group,
        group_name: str,
        datasets: dict[str, np.ndarray],
    ) -> None:
        grp = target.create_group(group_name)
        for ds_name, arr in datasets.items():
            grp.create_dataset(
                ds_name,
                data=arr,
                compression="gzip",
                compression_opts=_GZIP_LEVEL,
            )

    # ------------------------------------------------------------------
    # metadata/daq
    # ------------------------------------------------------------------

    @staticmethod
    def _write_daq(
        target: h5py.File | h5py.Group,
        daq: dict[str, Any],
    ) -> None:
        md = target.require_group("metadata")
        daq_grp = md.create_group("daq")
        for key, value in daq.items():
            if isinstance(value, bool):
                daq_grp.attrs[key] = np.bool_(value)
            elif isinstance(value, int):
                daq_grp.attrs[key] = np.int64(value)
            elif isinstance(value, float):
                daq_grp.attrs[key] = np.float64(value)
            elif isinstance(value, str):
                daq_grp.attrs[key] = value
            else:
                daq_grp.attrs[key] = value
