"""fd5.imaging.device_data — Device data product schema for device signals and acquisition logs.

Implements the ``device_data`` product schema per white-paper.md § device_data.
Handles time-series datasets (ECG, bellows, temperature, Prometheus metrics),
device_type attr, sampling_rate, and channel metadata following the NXlog/NXsensor pattern.
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np

_SCHEMA_VERSION = "1.0.0"

_GZIP_LEVEL = 4

_ID_INPUTS = ["timestamp", "scanner", "device_type"]

_VALID_DEVICE_TYPES = frozenset(
    {
        "blood_sampler",
        "motion_tracker",
        "infusion_pump",
        "physiological_monitor",
        "environmental_sensor",
    }
)


class DeviceDataSchema:
    """Product schema for device signals and acquisition logs (``device_data``)."""

    product_type: str = "device_data"
    schema_version: str = _SCHEMA_VERSION

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "device_data"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "domain": {"type": "string"},
                "device_type": {
                    "type": "string",
                    "enum": sorted(_VALID_DEVICE_TYPES),
                },
                "device_model": {"type": "string"},
                "recording_start": {"type": "string"},
                "recording_duration": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "number"},
                        "units": {"type": "string", "const": "s"},
                        "unitSI": {"type": "number"},
                    },
                },
                "metadata": {"type": "object"},
                "channels": {"type": "object"},
            },
            "required": [
                "_schema_version",
                "product",
                "name",
                "description",
                "device_type",
                "device_model",
                "recording_start",
            ],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {
            "product": "device_data",
            "domain": "medical_imaging",
        }

    def id_inputs(self) -> list[str]:
        return list(_ID_INPUTS)

    def write(self, target: h5py.File | h5py.Group, data: dict[str, Any]) -> None:
        """Write device data to *target*.

        *data* must contain:
        - ``device_type``: str — one of the valid device type categories
        - ``device_model``: str — model identifier
        - ``recording_start``: str — ISO 8601 timestamp
        - ``recording_duration``: float — total recording duration in seconds
        - ``channels``: dict mapping channel names to channel data dicts

        Each channel dict must contain:
        - ``signal``: numpy float64 array (N,)
        - ``time``: numpy float64 array (N,)
        - ``sampling_rate``: float — in Hz
        - ``units``: str — physical units for the signal
        - ``unitSI``: float — SI conversion factor
        - ``description``: str

        Optional channel keys:
        - ``measurement``, ``model``, ``run_control``
        - ``average_value``, ``minimum_value``, ``maximum_value``
        - ``cue_timestamp_zero``, ``cue_index``
        """
        target.attrs["device_type"] = data["device_type"]
        target.attrs["device_model"] = data["device_model"]
        target.attrs["recording_start"] = data["recording_start"]

        self._write_recording_duration(target, data["recording_duration"])
        self._write_metadata(target, data)
        self._write_channels(target, data["channels"])

    # ------------------------------------------------------------------
    # Recording duration
    # ------------------------------------------------------------------

    def _write_recording_duration(
        self,
        target: h5py.File | h5py.Group,
        duration: float,
    ) -> None:
        grp = target.create_group("recording_duration")
        grp.attrs["value"] = np.float64(duration)
        grp.attrs["units"] = "s"
        grp.attrs["unitSI"] = np.float64(1.0)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _write_metadata(
        self,
        target: h5py.File | h5py.Group,
        data: dict[str, Any],
    ) -> None:
        meta_grp = target.create_group("metadata")
        device_grp = meta_grp.create_group("device")
        device_grp.attrs["_type"] = data["device_type"]
        device_grp.attrs["_version"] = np.int64(1)
        device_grp.attrs["description"] = data.get(
            "device_description", f"{data['device_type']} device"
        )

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    def _write_channels(
        self,
        target: h5py.File | h5py.Group,
        channels: dict[str, dict[str, Any]],
    ) -> None:
        channels_grp = target.create_group("channels")
        for name, ch_data in channels.items():
            self._write_single_channel(channels_grp, name, ch_data)

    def _write_single_channel(
        self,
        channels_grp: h5py.Group,
        name: str,
        ch_data: dict[str, Any],
    ) -> None:
        ch_grp = channels_grp.create_group(name)

        ch_grp.attrs["_type"] = ch_data.get("_type", "signal")
        ch_grp.attrs["_version"] = np.int64(ch_data.get("_version", 1))
        ch_grp.attrs["description"] = ch_data["description"]

        if "model" in ch_data:
            ch_grp.attrs["model"] = ch_data["model"]
        if "measurement" in ch_data:
            ch_grp.attrs["measurement"] = ch_data["measurement"]
        if "run_control" in ch_data:
            ch_grp.attrs["run_control"] = np.bool_(ch_data["run_control"])

        self._write_sampling_rate(ch_grp, ch_data["sampling_rate"])
        self._write_signal(ch_grp, ch_data)
        self._write_time(ch_grp, ch_data)
        self._write_channel_statistics(ch_grp, ch_data)
        self._write_channel_duration(ch_grp, ch_data)
        self._write_cue_data(ch_grp, ch_data)

    def _write_sampling_rate(
        self,
        ch_grp: h5py.Group,
        sampling_rate: float,
    ) -> None:
        sr_grp = ch_grp.create_group("sampling_rate")
        sr_grp.attrs["value"] = np.float64(sampling_rate)
        sr_grp.attrs["units"] = "Hz"
        sr_grp.attrs["unitSI"] = np.float64(1.0)

    def _write_signal(
        self,
        ch_grp: h5py.Group,
        ch_data: dict[str, Any],
    ) -> None:
        signal = np.asarray(ch_data["signal"], dtype=np.float64)
        ds = ch_grp.create_dataset(
            "signal",
            data=signal,
            compression="gzip",
            compression_opts=_GZIP_LEVEL,
        )
        ds.attrs["units"] = ch_data["units"]
        ds.attrs["unitSI"] = np.float64(ch_data["unitSI"])
        ds.attrs["description"] = ch_data["description"]

    def _write_time(
        self,
        ch_grp: h5py.Group,
        ch_data: dict[str, Any],
    ) -> None:
        time_arr = np.asarray(ch_data["time"], dtype=np.float64)
        ds = ch_grp.create_dataset(
            "time",
            data=time_arr,
            compression="gzip",
            compression_opts=_GZIP_LEVEL,
        )
        ds.attrs["units"] = "s"
        ds.attrs["unitSI"] = np.float64(1.0)
        if "time_start" in ch_data:
            ds.attrs["start"] = ch_data["time_start"]

    def _write_channel_statistics(
        self,
        ch_grp: h5py.Group,
        ch_data: dict[str, Any],
    ) -> None:
        for stat_key in ("average_value", "minimum_value", "maximum_value"):
            if stat_key in ch_data:
                ch_grp.attrs[stat_key] = np.float64(ch_data[stat_key])

    def _write_channel_duration(
        self,
        ch_grp: h5py.Group,
        ch_data: dict[str, Any],
    ) -> None:
        if "duration" not in ch_data:
            return
        dur_grp = ch_grp.create_group("duration")
        dur_grp.attrs["value"] = np.float64(ch_data["duration"])
        dur_grp.attrs["units"] = "s"
        dur_grp.attrs["unitSI"] = np.float64(1.0)

    def _write_cue_data(
        self,
        ch_grp: h5py.Group,
        ch_data: dict[str, Any],
    ) -> None:
        if "cue_timestamp_zero" in ch_data:
            ch_grp.create_dataset(
                "cue_timestamp_zero",
                data=np.asarray(ch_data["cue_timestamp_zero"], dtype=np.float64),
            )
        if "cue_index" in ch_data:
            ch_grp.create_dataset(
                "cue_index",
                data=np.asarray(ch_data["cue_index"], dtype=np.int64),
            )
