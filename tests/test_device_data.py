"""Tests for fd5.imaging.device_data — DeviceDataSchema product schema."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from fd5.registry import ProductSchema, register_schema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def schema():
    from fd5.imaging.device_data import DeviceDataSchema

    return DeviceDataSchema()


@pytest.fixture()
def h5file(tmp_path):
    path = tmp_path / "device_data.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path):
    return tmp_path / "device_data.h5"


def _make_signal(n_samples=1000, freq=1.0, sampling_rate=500.0):
    rng = np.random.default_rng(42)
    t = np.arange(n_samples, dtype=np.float64) / sampling_rate
    signal = np.sin(2 * np.pi * freq * t) + 0.1 * rng.standard_normal(n_samples)
    return signal, t


def _minimal_channel_data(n_samples=100, sampling_rate=500.0):
    signal, time = _make_signal(n_samples=n_samples, sampling_rate=sampling_rate)
    return {
        "signal": signal,
        "time": time,
        "sampling_rate": sampling_rate,
        "units": "mV",
        "unitSI": 0.001,
        "description": "ECG lead II signal",
        "_type": "signal",
        "_version": 1,
    }


def _minimal_data():
    return {
        "device_type": "physiological_monitor",
        "device_model": "GE CARESCAPE B650",
        "recording_start": "2024-07-24T19:06:10+02:00",
        "recording_duration": 300.0,
        "channels": {
            "ecg_lead_ii": _minimal_channel_data(),
        },
    }


def _multi_channel_data():
    ecg = _minimal_channel_data()
    ecg["measurement"] = "ecg"
    ecg["model"] = "3-lead"
    ecg["run_control"] = True

    resp_signal, resp_time = _make_signal(n_samples=50, freq=0.25, sampling_rate=25.0)
    resp = {
        "signal": resp_signal,
        "time": resp_time,
        "sampling_rate": 25.0,
        "units": "a.u.",
        "unitSI": 1.0,
        "description": "Bellows respiratory signal",
        "measurement": "respiratory",
        "run_control": False,
        "average_value": float(np.mean(resp_signal)),
        "minimum_value": float(np.min(resp_signal)),
        "maximum_value": float(np.max(resp_signal)),
        "duration": 2.0,
    }
    return {
        "device_type": "physiological_monitor",
        "device_model": "Anzai AZ-733V",
        "recording_start": "2024-07-24T19:06:10+02:00",
        "recording_duration": 600.0,
        "device_description": "Respiratory and cardiac monitor",
        "channels": {
            "ecg_lead_ii": ecg,
            "respiratory": resp,
        },
    }


def _environmental_sensor_data():
    temp_signal = np.linspace(20.0, 21.5, 60, dtype=np.float64)
    temp_time = np.arange(60, dtype=np.float64)
    return {
        "device_type": "environmental_sensor",
        "device_model": "Sensirion SHT45",
        "recording_start": "2024-07-24T10:00:00Z",
        "recording_duration": 59.0,
        "channels": {
            "room_temperature": {
                "signal": temp_signal,
                "time": temp_time,
                "sampling_rate": 1.0,
                "units": "degC",
                "unitSI": 1.0,
                "description": "Room temperature",
                "time_start": "2024-07-24T10:00:00Z",
            },
        },
    }


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_product_schema_protocol(self, schema):
        assert isinstance(schema, ProductSchema)

    def test_product_type_is_device_data(self, schema):
        assert schema.product_type == "device_data"

    def test_schema_version_is_string(self, schema):
        assert isinstance(schema.schema_version, str)

    def test_has_required_methods(self, schema):
        assert callable(schema.json_schema)
        assert callable(schema.required_root_attrs)
        assert callable(schema.write)
        assert callable(schema.id_inputs)


# ---------------------------------------------------------------------------
# json_schema()
# ---------------------------------------------------------------------------


class TestJsonSchema:
    def test_returns_dict(self, schema):
        result = schema.json_schema()
        assert isinstance(result, dict)

    def test_has_draft_2020_12_meta(self, schema):
        result = schema.json_schema()
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_product_const_is_device_data(self, schema):
        result = schema.json_schema()
        assert result["properties"]["product"]["const"] == "device_data"

    def test_device_type_enum(self, schema):
        result = schema.json_schema()
        device_type_prop = result["properties"]["device_type"]
        assert "enum" in device_type_prop
        expected = sorted(
            [
                "blood_sampler",
                "motion_tracker",
                "infusion_pump",
                "physiological_monitor",
                "environmental_sensor",
            ]
        )
        assert device_type_prop["enum"] == expected

    def test_has_channels_property(self, schema):
        result = schema.json_schema()
        assert "channels" in result["properties"]

    def test_has_recording_duration_property(self, schema):
        result = schema.json_schema()
        assert "recording_duration" in result["properties"]

    def test_required_fields(self, schema):
        result = schema.json_schema()
        required = result["required"]
        for field in [
            "_schema_version",
            "product",
            "name",
            "description",
            "device_type",
            "device_model",
            "recording_start",
        ]:
            assert field in required

    def test_valid_json_schema(self, schema):
        import jsonschema

        result = schema.json_schema()
        jsonschema.Draft202012Validator.check_schema(result)


# ---------------------------------------------------------------------------
# required_root_attrs()
# ---------------------------------------------------------------------------


class TestRequiredRootAttrs:
    def test_returns_dict(self, schema):
        result = schema.required_root_attrs()
        assert isinstance(result, dict)

    def test_contains_product_device_data(self, schema):
        result = schema.required_root_attrs()
        assert result["product"] == "device_data"

    def test_contains_domain(self, schema):
        result = schema.required_root_attrs()
        assert result["domain"] == "medical_imaging"


# ---------------------------------------------------------------------------
# id_inputs()
# ---------------------------------------------------------------------------


class TestIdInputs:
    def test_returns_list_of_strings(self, schema):
        result = schema.id_inputs()
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_contains_expected_inputs(self, schema):
        result = schema.id_inputs()
        assert "timestamp" in result
        assert "scanner" in result
        assert "device_type" in result


# ---------------------------------------------------------------------------
# write() — root attributes and recording_duration
# ---------------------------------------------------------------------------


class TestWriteRootAttrs:
    def test_writes_device_type(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert h5file.attrs["device_type"] == "physiological_monitor"

    def test_writes_device_model(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert h5file.attrs["device_model"] == "GE CARESCAPE B650"

    def test_writes_recording_start(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert h5file.attrs["recording_start"] == "2024-07-24T19:06:10+02:00"

    def test_recording_duration_group(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert "recording_duration" in h5file
        grp = h5file["recording_duration"]
        assert isinstance(grp, h5py.Group)
        assert grp.attrs["value"] == pytest.approx(300.0)
        assert grp.attrs["units"] == "s"
        assert grp.attrs["unitSI"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# write() — metadata
# ---------------------------------------------------------------------------


class TestWriteMetadata:
    def test_metadata_group_exists(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert "metadata" in h5file
        assert "device" in h5file["metadata"]

    def test_metadata_device_attrs(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        device = h5file["metadata/device"]
        assert device.attrs["_type"] == "physiological_monitor"
        assert device.attrs["_version"] == 1
        assert "description" in device.attrs

    def test_custom_device_description(self, schema, h5file):
        data = _multi_channel_data()
        schema.write(h5file, data)
        device = h5file["metadata/device"]
        assert device.attrs["description"] == "Respiratory and cardiac monitor"


# ---------------------------------------------------------------------------
# write() — channels (single)
# ---------------------------------------------------------------------------


class TestWriteSingleChannel:
    def test_channels_group_exists(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert "channels" in h5file

    def test_channel_subgroup_exists(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert "ecg_lead_ii" in h5file["channels"]

    def test_channel_attrs(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        ch = h5file["channels/ecg_lead_ii"]
        assert ch.attrs["_type"] == "signal"
        assert ch.attrs["_version"] == 1
        assert ch.attrs["description"] == "ECG lead II signal"

    def test_sampling_rate_group(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        sr = h5file["channels/ecg_lead_ii/sampling_rate"]
        assert isinstance(sr, h5py.Group)
        assert sr.attrs["value"] == pytest.approx(500.0)
        assert sr.attrs["units"] == "Hz"
        assert sr.attrs["unitSI"] == pytest.approx(1.0)

    def test_signal_dataset(self, schema, h5file):
        data = _minimal_data()
        schema.write(h5file, data)
        ds = h5file["channels/ecg_lead_ii/signal"]
        assert ds.dtype == np.float64
        assert ds.shape == (100,)
        np.testing.assert_array_almost_equal(
            ds[:], data["channels"]["ecg_lead_ii"]["signal"]
        )

    def test_signal_attrs(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        ds = h5file["channels/ecg_lead_ii/signal"]
        assert ds.attrs["units"] == "mV"
        assert ds.attrs["unitSI"] == pytest.approx(0.001)
        assert "description" in ds.attrs

    def test_signal_compression(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        ds = h5file["channels/ecg_lead_ii/signal"]
        assert ds.compression == "gzip"
        assert ds.compression_opts == 4

    def test_time_dataset(self, schema, h5file):
        data = _minimal_data()
        schema.write(h5file, data)
        ds = h5file["channels/ecg_lead_ii/time"]
        assert ds.dtype == np.float64
        assert ds.shape == (100,)
        np.testing.assert_array_almost_equal(
            ds[:], data["channels"]["ecg_lead_ii"]["time"]
        )

    def test_time_attrs(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        ds = h5file["channels/ecg_lead_ii/time"]
        assert ds.attrs["units"] == "s"
        assert ds.attrs["unitSI"] == pytest.approx(1.0)

    def test_time_compression(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        ds = h5file["channels/ecg_lead_ii/time"]
        assert ds.compression == "gzip"
        assert ds.compression_opts == 4


# ---------------------------------------------------------------------------
# write() — channels (multi with optional attrs)
# ---------------------------------------------------------------------------


class TestWriteMultiChannel:
    def test_both_channels_exist(self, schema, h5file):
        schema.write(h5file, _multi_channel_data())
        assert "ecg_lead_ii" in h5file["channels"]
        assert "respiratory" in h5file["channels"]

    def test_measurement_attr(self, schema, h5file):
        schema.write(h5file, _multi_channel_data())
        ecg = h5file["channels/ecg_lead_ii"]
        assert ecg.attrs["measurement"] == "ecg"

    def test_model_attr(self, schema, h5file):
        schema.write(h5file, _multi_channel_data())
        ecg = h5file["channels/ecg_lead_ii"]
        assert ecg.attrs["model"] == "3-lead"

    def test_run_control_attr(self, schema, h5file):
        schema.write(h5file, _multi_channel_data())
        ecg = h5file["channels/ecg_lead_ii"]
        assert ecg.attrs["run_control"] is np.True_
        resp = h5file["channels/respiratory"]
        assert resp.attrs["run_control"] is np.False_

    def test_statistics_attrs(self, schema, h5file):
        data = _multi_channel_data()
        schema.write(h5file, data)
        resp = h5file["channels/respiratory"]
        assert "average_value" in resp.attrs
        assert "minimum_value" in resp.attrs
        assert "maximum_value" in resp.attrs
        assert resp.attrs["average_value"] == pytest.approx(
            data["channels"]["respiratory"]["average_value"]
        )

    def test_channel_duration_group(self, schema, h5file):
        schema.write(h5file, _multi_channel_data())
        dur = h5file["channels/respiratory/duration"]
        assert isinstance(dur, h5py.Group)
        assert dur.attrs["value"] == pytest.approx(2.0)
        assert dur.attrs["units"] == "s"
        assert dur.attrs["unitSI"] == pytest.approx(1.0)

    def test_no_duration_when_absent(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert "duration" not in h5file["channels/ecg_lead_ii"]

    def test_no_statistics_when_absent(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        ch = h5file["channels/ecg_lead_ii"]
        assert "average_value" not in ch.attrs
        assert "minimum_value" not in ch.attrs
        assert "maximum_value" not in ch.attrs


# ---------------------------------------------------------------------------
# write() — time_start and cue data
# ---------------------------------------------------------------------------


class TestWriteTimeStartAndCue:
    def test_time_start_attr(self, schema, h5file):
        data = _environmental_sensor_data()
        schema.write(h5file, data)
        ds = h5file["channels/room_temperature/time"]
        assert ds.attrs["start"] == "2024-07-24T10:00:00Z"

    def test_no_start_when_absent(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        ds = h5file["channels/ecg_lead_ii/time"]
        assert "start" not in ds.attrs

    def test_cue_datasets(self, schema, h5file):
        data = _minimal_data()
        ch = data["channels"]["ecg_lead_ii"]
        ch["cue_timestamp_zero"] = np.array([0.0, 10.0, 20.0])
        ch["cue_index"] = np.array([0, 5000, 10000])
        schema.write(h5file, data)
        ch_grp = h5file["channels/ecg_lead_ii"]
        assert "cue_timestamp_zero" in ch_grp
        assert "cue_index" in ch_grp
        np.testing.assert_array_equal(
            ch_grp["cue_timestamp_zero"][:], [0.0, 10.0, 20.0]
        )
        np.testing.assert_array_equal(ch_grp["cue_index"][:], [0, 5000, 10000])

    def test_no_cue_when_absent(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        ch = h5file["channels/ecg_lead_ii"]
        assert "cue_timestamp_zero" not in ch
        assert "cue_index" not in ch


# ---------------------------------------------------------------------------
# write() — different device types
# ---------------------------------------------------------------------------


class TestWriteDeviceTypes:
    def test_environmental_sensor(self, schema, h5file):
        schema.write(h5file, _environmental_sensor_data())
        assert h5file.attrs["device_type"] == "environmental_sensor"
        assert h5file["metadata/device"].attrs["_type"] == "environmental_sensor"

    def test_blood_sampler(self, schema, h5file):
        data = _minimal_data()
        data["device_type"] = "blood_sampler"
        data["device_model"] = "ABSS Allogg"
        schema.write(h5file, data)
        assert h5file.attrs["device_type"] == "blood_sampler"


# ---------------------------------------------------------------------------
# Round-trip: write then read back
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_signal_data_survives_roundtrip(self, schema, h5path):
        data = _minimal_data()
        original_signal = data["channels"]["ecg_lead_ii"]["signal"].copy()
        original_time = data["channels"]["ecg_lead_ii"]["time"].copy()

        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            read_signal = f["channels/ecg_lead_ii/signal"][:]
            read_time = f["channels/ecg_lead_ii/time"][:]

        np.testing.assert_array_almost_equal(read_signal, original_signal)
        np.testing.assert_array_almost_equal(read_time, original_time)

    def test_multi_channel_roundtrip(self, schema, h5path):
        data = _multi_channel_data()
        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            assert "ecg_lead_ii" in f["channels"]
            assert "respiratory" in f["channels"]
            ecg_signal = f["channels/ecg_lead_ii/signal"][:]
            resp_signal = f["channels/respiratory/signal"][:]

        np.testing.assert_array_almost_equal(
            ecg_signal, data["channels"]["ecg_lead_ii"]["signal"]
        )
        np.testing.assert_array_almost_equal(
            resp_signal, data["channels"]["respiratory"]["signal"]
        )

    def test_attrs_survive_roundtrip(self, schema, h5path):
        data = _minimal_data()
        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            assert f.attrs["device_type"] == "physiological_monitor"
            assert f.attrs["device_model"] == "GE CARESCAPE B650"
            assert f.attrs["recording_start"] == "2024-07-24T19:06:10+02:00"
            assert f["recording_duration"].attrs["value"] == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# Entry point registration (manual via register_schema)
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_factory_returns_device_data_schema(self):
        from fd5.imaging.device_data import DeviceDataSchema

        instance = DeviceDataSchema()
        assert instance.product_type == "device_data"

    def test_register_and_retrieve(self):
        from fd5.imaging.device_data import DeviceDataSchema
        from fd5.registry import get_schema

        register_schema("device_data", DeviceDataSchema())
        retrieved = get_schema("device_data")
        assert retrieved.product_type == "device_data"


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_create_validate_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _minimal_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-device-data"
            f.attrs["description"] = "Integration test device_data file"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_generate_schema_for_device_data(self, schema):
        register_schema("device_data", schema)
        from fd5.schema import generate_schema

        result = generate_schema("device_data")
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert result["properties"]["product"]["const"] == "device_data"

    def test_idempotent_write(self, schema, h5path):
        """Writing the same data to two separate files produces identical structures."""
        data = _minimal_data()

        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        h5path2 = h5path.parent / "device_data_2.h5"
        with h5py.File(h5path2, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f1, h5py.File(h5path2, "r") as f2:
            assert f1.attrs["device_type"] == f2.attrs["device_type"]
            np.testing.assert_array_equal(
                f1["channels/ecg_lead_ii/signal"][:],
                f2["channels/ecg_lead_ii/signal"][:],
            )
