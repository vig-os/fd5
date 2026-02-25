"""Tests for fd5.imaging.listmode — ListmodeSchema product schema."""

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
    from fd5.imaging.listmode import ListmodeSchema

    return ListmodeSchema()


@pytest.fixture()
def h5file(tmp_path):
    path = tmp_path / "listmode.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path):
    return tmp_path / "listmode.h5"


# ---------------------------------------------------------------------------
# Helpers — compound dtypes and data builders
# ---------------------------------------------------------------------------

_SINGLES_DTYPE = np.dtype(
    [
        ("timestamp", np.uint64),
        ("energy", np.float32),
        ("detector_id", np.uint32),
    ]
)

_TIME_MARKERS_DTYPE = np.dtype(
    [
        ("timestamp", np.uint64),
        ("marker_type", np.uint8),
    ]
)

_COIN_COUNTERS_DTYPE = np.dtype(
    [
        ("timestamp", np.uint64),
        ("prompt", np.uint32),
        ("delayed", np.uint32),
    ]
)

_TABLE_POSITIONS_DTYPE = np.dtype(
    [
        ("timestamp", np.uint64),
        ("position", np.float32),
    ]
)

_EVENTS_2P_DTYPE = np.dtype(
    [
        ("timestamp", np.uint64),
        ("energy_a", np.float32),
        ("energy_b", np.float32),
        ("detector_a", np.uint32),
        ("detector_b", np.uint32),
    ]
)


def _make_singles(n: int = 100) -> np.ndarray:
    rng = np.random.default_rng(42)
    arr = np.empty(n, dtype=_SINGLES_DTYPE)
    arr["timestamp"] = np.sort(rng.integers(0, 10**9, size=n, dtype=np.uint64))
    arr["energy"] = rng.uniform(100, 700, size=n).astype(np.float32)
    arr["detector_id"] = rng.integers(0, 1024, size=n, dtype=np.uint32)
    return arr


def _make_time_markers(n: int = 20) -> np.ndarray:
    rng = np.random.default_rng(43)
    arr = np.empty(n, dtype=_TIME_MARKERS_DTYPE)
    arr["timestamp"] = np.sort(rng.integers(0, 10**9, size=n, dtype=np.uint64))
    arr["marker_type"] = rng.integers(0, 4, size=n, dtype=np.uint8)
    return arr


def _make_coin_counters(n: int = 50) -> np.ndarray:
    rng = np.random.default_rng(44)
    arr = np.empty(n, dtype=_COIN_COUNTERS_DTYPE)
    arr["timestamp"] = np.sort(rng.integers(0, 10**9, size=n, dtype=np.uint64))
    arr["prompt"] = rng.integers(0, 1000, size=n, dtype=np.uint32)
    arr["delayed"] = rng.integers(0, 500, size=n, dtype=np.uint32)
    return arr


def _make_table_positions(n: int = 10) -> np.ndarray:
    rng = np.random.default_rng(45)
    arr = np.empty(n, dtype=_TABLE_POSITIONS_DTYPE)
    arr["timestamp"] = np.sort(rng.integers(0, 10**9, size=n, dtype=np.uint64))
    arr["position"] = rng.uniform(0, 200, size=n).astype(np.float32)
    return arr


def _make_events_2p(n: int = 80) -> np.ndarray:
    rng = np.random.default_rng(46)
    arr = np.empty(n, dtype=_EVENTS_2P_DTYPE)
    arr["timestamp"] = np.sort(rng.integers(0, 10**9, size=n, dtype=np.uint64))
    arr["energy_a"] = rng.uniform(400, 600, size=n).astype(np.float32)
    arr["energy_b"] = rng.uniform(400, 600, size=n).astype(np.float32)
    arr["detector_a"] = rng.integers(0, 1024, size=n, dtype=np.uint32)
    arr["detector_b"] = rng.integers(0, 1024, size=n, dtype=np.uint32)
    return arr


def _minimal_data() -> dict:
    return {
        "mode": "3d",
        "table_pos": 150.0,
        "duration": 600.0,
        "z_min": -100.0,
        "z_max": 100.0,
        "raw_data": {
            "singles": _make_singles(50),
            "time_markers": _make_time_markers(10),
        },
    }


def _full_raw_data() -> dict:
    return {
        "mode": "3d",
        "table_pos": 200.0,
        "duration": 1200.0,
        "z_min": -150.0,
        "z_max": 150.0,
        "raw_data": {
            "singles": _make_singles(100),
            "time_markers": _make_time_markers(20),
            "coin_counters": _make_coin_counters(50),
            "table_positions": _make_table_positions(10),
        },
        "daq": {
            "acq_mode": "listmode",
            "gain_cal": 1.05,
            "energy_cal": True,
        },
    }


def _proc_data_only() -> dict:
    return {
        "mode": "2d",
        "table_pos": 100.0,
        "duration": 300.0,
        "z_min": -50.0,
        "z_max": 50.0,
        "proc_data": {
            "events_2p": _make_events_2p(80),
        },
    }


def _raw_and_proc_data() -> dict:
    return {
        "mode": "3d",
        "table_pos": 175.0,
        "duration": 900.0,
        "z_min": -120.0,
        "z_max": 120.0,
        "raw_data": {
            "singles": _make_singles(60),
        },
        "proc_data": {
            "events_2p": _make_events_2p(40),
        },
    }


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_product_schema_protocol(self, schema):
        assert isinstance(schema, ProductSchema)

    def test_product_type_is_listmode(self, schema):
        assert schema.product_type == "listmode"

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

    def test_product_const_is_listmode(self, schema):
        result = schema.json_schema()
        assert result["properties"]["product"]["const"] == "listmode"

    def test_has_listmode_specific_properties(self, schema):
        result = schema.json_schema()
        props = result["properties"]
        for key in ("mode", "table_pos", "duration", "z_min", "z_max"):
            assert key in props, f"{key} missing from json_schema properties"

    def test_has_metadata_property(self, schema):
        result = schema.json_schema()
        assert "metadata" in result["properties"]

    def test_has_raw_data_property(self, schema):
        result = schema.json_schema()
        assert "raw_data" in result["properties"]

    def test_has_proc_data_property(self, schema):
        result = schema.json_schema()
        assert "proc_data" in result["properties"]

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

    def test_contains_product_listmode(self, schema):
        result = schema.required_root_attrs()
        assert result["product"] == "listmode"

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

    def test_follows_medical_imaging_convention(self, schema):
        result = schema.id_inputs()
        assert "timestamp" in result
        assert "scanner" in result
        assert "vendor_series_id" in result

    def test_returns_copy(self, schema):
        a = schema.id_inputs()
        b = schema.id_inputs()
        assert a == b
        assert a is not b


# ---------------------------------------------------------------------------
# write() — root attributes
# ---------------------------------------------------------------------------


class TestWriteRootAttrs:
    def test_writes_mode_attr(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert h5file.attrs["mode"] == "3d"

    def test_writes_table_pos_attr(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert h5file.attrs["table_pos"] == pytest.approx(150.0)
        assert h5file.attrs["table_pos"].dtype == np.float64

    def test_writes_duration_attr(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert h5file.attrs["duration"] == pytest.approx(600.0)

    def test_writes_z_min_attr(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert h5file.attrs["z_min"] == pytest.approx(-100.0)

    def test_writes_z_max_attr(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert h5file.attrs["z_max"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# write() — raw_data group
# ---------------------------------------------------------------------------


class TestWriteRawData:
    def test_raw_data_group_created(self, schema, h5file):
        schema.write(h5file, _minimal_data())
        assert "raw_data" in h5file
        assert isinstance(h5file["raw_data"], h5py.Group)

    def test_singles_dataset(self, schema, h5file):
        data = _minimal_data()
        schema.write(h5file, data)
        ds = h5file["raw_data/singles"]
        assert ds.shape == (50,)
        assert ds.dtype == _SINGLES_DTYPE

    def test_singles_round_trip(self, schema, h5file):
        data = _minimal_data()
        schema.write(h5file, data)
        stored = h5file["raw_data/singles"][:]
        np.testing.assert_array_equal(stored, data["raw_data"]["singles"])

    def test_time_markers_dataset(self, schema, h5file):
        data = _minimal_data()
        schema.write(h5file, data)
        ds = h5file["raw_data/time_markers"]
        assert ds.shape == (10,)
        assert ds.dtype == _TIME_MARKERS_DTYPE

    def test_time_markers_round_trip(self, schema, h5file):
        data = _minimal_data()
        schema.write(h5file, data)
        stored = h5file["raw_data/time_markers"][:]
        np.testing.assert_array_equal(stored, data["raw_data"]["time_markers"])

    def test_full_raw_data_all_datasets(self, schema, h5file):
        data = _full_raw_data()
        schema.write(h5file, data)
        grp = h5file["raw_data"]
        assert "singles" in grp
        assert "time_markers" in grp
        assert "coin_counters" in grp
        assert "table_positions" in grp

    def test_coin_counters_round_trip(self, schema, h5file):
        data = _full_raw_data()
        schema.write(h5file, data)
        stored = h5file["raw_data/coin_counters"][:]
        np.testing.assert_array_equal(stored, data["raw_data"]["coin_counters"])

    def test_table_positions_round_trip(self, schema, h5file):
        data = _full_raw_data()
        schema.write(h5file, data)
        stored = h5file["raw_data/table_positions"][:]
        np.testing.assert_array_equal(stored, data["raw_data"]["table_positions"])

    def test_raw_data_compression(self, schema, h5file):
        data = _minimal_data()
        schema.write(h5file, data)
        ds = h5file["raw_data/singles"]
        assert ds.compression == "gzip"
        assert ds.compression_opts == 4

    def test_no_raw_data_when_absent(self, schema, h5file):
        data = _proc_data_only()
        schema.write(h5file, data)
        assert "raw_data" not in h5file


# ---------------------------------------------------------------------------
# write() — proc_data group
# ---------------------------------------------------------------------------


class TestWriteProcData:
    def test_proc_data_group_created(self, schema, h5file):
        data = _proc_data_only()
        schema.write(h5file, data)
        assert "proc_data" in h5file
        assert isinstance(h5file["proc_data"], h5py.Group)

    def test_events_2p_dataset(self, schema, h5file):
        data = _proc_data_only()
        schema.write(h5file, data)
        ds = h5file["proc_data/events_2p"]
        assert ds.shape == (80,)
        assert ds.dtype == _EVENTS_2P_DTYPE

    def test_events_2p_round_trip(self, schema, h5file):
        data = _proc_data_only()
        schema.write(h5file, data)
        stored = h5file["proc_data/events_2p"][:]
        np.testing.assert_array_equal(stored, data["proc_data"]["events_2p"])

    def test_proc_data_compression(self, schema, h5file):
        data = _proc_data_only()
        schema.write(h5file, data)
        ds = h5file["proc_data/events_2p"]
        assert ds.compression == "gzip"
        assert ds.compression_opts == 4

    def test_no_proc_data_when_absent(self, schema, h5file):
        data = _minimal_data()
        schema.write(h5file, data)
        assert "proc_data" not in h5file


# ---------------------------------------------------------------------------
# write() — both raw_data and proc_data
# ---------------------------------------------------------------------------


class TestWriteRawAndProc:
    def test_both_groups_present(self, schema, h5file):
        data = _raw_and_proc_data()
        schema.write(h5file, data)
        assert "raw_data" in h5file
        assert "proc_data" in h5file

    def test_raw_and_proc_round_trip(self, schema, h5file):
        data = _raw_and_proc_data()
        schema.write(h5file, data)
        raw_stored = h5file["raw_data/singles"][:]
        np.testing.assert_array_equal(raw_stored, data["raw_data"]["singles"])
        proc_stored = h5file["proc_data/events_2p"][:]
        np.testing.assert_array_equal(proc_stored, data["proc_data"]["events_2p"])


# ---------------------------------------------------------------------------
# write() — metadata/daq
# ---------------------------------------------------------------------------


class TestWriteDaq:
    def test_daq_group_created(self, schema, h5file):
        data = _full_raw_data()
        schema.write(h5file, data)
        assert "metadata" in h5file
        assert "daq" in h5file["metadata"]
        assert isinstance(h5file["metadata/daq"], h5py.Group)

    def test_daq_string_attr(self, schema, h5file):
        data = _full_raw_data()
        schema.write(h5file, data)
        daq = h5file["metadata/daq"]
        val = daq.attrs["acq_mode"]
        if isinstance(val, bytes):
            val = val.decode()
        assert val == "listmode"

    def test_daq_float_attr(self, schema, h5file):
        data = _full_raw_data()
        schema.write(h5file, data)
        daq = h5file["metadata/daq"]
        assert daq.attrs["gain_cal"] == pytest.approx(1.05)

    def test_daq_bool_attr(self, schema, h5file):
        data = _full_raw_data()
        schema.write(h5file, data)
        daq = h5file["metadata/daq"]
        assert bool(daq.attrs["energy_cal"]) is True

    def test_no_metadata_when_no_daq(self, schema, h5file):
        data = _minimal_data()
        schema.write(h5file, data)
        assert "metadata" not in h5file


# ---------------------------------------------------------------------------
# Entry point registration (manual via register_schema)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# write() — metadata/daq int and fallthrough (listmode.py:154,160)
# ---------------------------------------------------------------------------


class TestWriteDaqIntAndFallthrough:
    def test_daq_int_attr(self, schema, h5file):
        """Covers listmode.py:154 — _write_daq with int value."""
        data = _minimal_data()
        data["daq"] = {"n_channels": 1024}
        schema.write(h5file, data)
        daq = h5file["metadata/daq"]
        assert int(daq.attrs["n_channels"]) == 1024

    def test_daq_fallthrough_attr(self, schema, h5file):
        """Covers listmode.py:160 — _write_daq else branch (e.g. numpy array)."""
        data = _minimal_data()
        data["daq"] = {"offsets": np.array([1.0, 2.0], dtype=np.float64)}
        schema.write(h5file, data)
        daq = h5file["metadata/daq"]
        np.testing.assert_array_equal(daq.attrs["offsets"], [1.0, 2.0])


# ---------------------------------------------------------------------------
# Entry point registration (manual via register_schema)
# ---------------------------------------------------------------------------


class TestEntryPointRegistration:
    def test_factory_returns_listmode_schema(self):
        from fd5.imaging.listmode import ListmodeSchema

        instance = ListmodeSchema()
        assert instance.product_type == "listmode"

    def test_register_and_retrieve(self):
        from fd5.imaging.listmode import ListmodeSchema
        from fd5.registry import get_schema

        instance = ListmodeSchema()
        register_schema("listmode", instance)
        retrieved = get_schema("listmode")
        assert retrieved.product_type == "listmode"


# ---------------------------------------------------------------------------
# Integration — round-trip write → validate
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_create_validate_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _minimal_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-listmode"
            f.attrs["description"] = "Integration test listmode file"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_full_data_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _full_raw_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "full-listmode"
            f.attrs["description"] = "Full listmode with DAQ metadata"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

        with h5py.File(h5path, "r") as f:
            assert f.attrs["mode"] == "3d"
            assert f.attrs["duration"] == pytest.approx(1200.0)
            assert "raw_data" in f
            assert "singles" in f["raw_data"]
            assert "metadata/daq" in f
            val = f["metadata/daq"].attrs["acq_mode"]
            if isinstance(val, bytes):
                val = val.decode()
            assert val == "listmode"

    def test_generate_schema_for_listmode(self, schema):
        register_schema("listmode", schema)
        from fd5.schema import generate_schema

        result = generate_schema("listmode")
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert result["properties"]["product"]["const"] == "listmode"

    def test_proc_data_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _proc_data_only()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "proc-only-listmode"
            f.attrs["description"] = "Listmode with processed events only"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

        with h5py.File(h5path, "r") as f:
            assert f.attrs["mode"] == "2d"
            assert "raw_data" not in f
            assert "proc_data" in f
            stored = f["proc_data/events_2p"][:]
            np.testing.assert_array_equal(stored, data["proc_data"]["events_2p"])

    def test_raw_and_proc_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _raw_and_proc_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "mixed-listmode"
            f.attrs["description"] = "Listmode with raw and processed data"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]
