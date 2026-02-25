"""Tests for fd5.imaging.sim — SimSchema product schema."""

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
    from fd5.imaging.sim import SimSchema

    return SimSchema()


@pytest.fixture()
def h5file(tmp_path):
    path = tmp_path / "sim.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path):
    return tmp_path / "sim.h5"


def _make_volume_3d(shape=(16, 32, 32)):
    return np.random.default_rng(42).random(shape, dtype=np.float32)


def _make_events_2p(n=100):
    dt = np.dtype(
        [
            ("time", np.float64),
            ("energy_1", np.float32),
            ("energy_2", np.float32),
            ("x_1", np.float32),
            ("x_2", np.float32),
        ]
    )
    rng = np.random.default_rng(42)
    arr = np.empty(n, dtype=dt)
    arr["time"] = rng.random(n)
    arr["energy_1"] = rng.random(n).astype(np.float32)
    arr["energy_2"] = rng.random(n).astype(np.float32)
    arr["x_1"] = rng.random(n).astype(np.float32)
    arr["x_2"] = rng.random(n).astype(np.float32)
    return arr


def _make_events_3p(n=50):
    dt = np.dtype(
        [
            ("time", np.float64),
            ("energy_1", np.float32),
            ("energy_2", np.float32),
            ("energy_3", np.float32),
        ]
    )
    rng = np.random.default_rng(99)
    arr = np.empty(n, dtype=dt)
    arr["time"] = rng.random(n)
    arr["energy_1"] = rng.random(n).astype(np.float32)
    arr["energy_2"] = rng.random(n).astype(np.float32)
    arr["energy_3"] = rng.random(n).astype(np.float32)
    return arr


def _minimal_ground_truth():
    return {
        "ground_truth": {
            "activity": _make_volume_3d((8, 16, 16)),
            "attenuation": _make_volume_3d((8, 16, 16)),
        },
    }


def _full_sim_data():
    return {
        "ground_truth": {
            "activity": _make_volume_3d((8, 16, 16)),
            "attenuation": _make_volume_3d((8, 16, 16)),
        },
        "events": {
            "events_2p": _make_events_2p(100),
            "events_3p": _make_events_3p(50),
        },
        "simulation": {
            "_type": "gate",
            "_version": 1,
            "gate_version": "9.3",
            "physics_list": "QGSP_BERT_HP_EMZ",
            "n_primaries": 1000000,
            "random_seed": 12345,
            "geometry": {
                "phantom": "XCAT",
            },
            "source": {
                "activity_distribution": "uniform",
                "activities": "37.0 MBq",
            },
        },
    }


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_product_schema_protocol(self, schema):
        assert isinstance(schema, ProductSchema)

    def test_product_type_is_sim(self, schema):
        assert schema.product_type == "sim"

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

    def test_product_const_is_sim(self, schema):
        result = schema.json_schema()
        assert result["properties"]["product"]["const"] == "sim"

    def test_requires_ground_truth(self, schema):
        result = schema.json_schema()
        assert "ground_truth" in result.get(
            "required", []
        ) or "ground_truth" in result.get("properties", {})

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

    def test_contains_product_sim(self, schema):
        result = schema.required_root_attrs()
        assert result["product"] == "sim"

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

    def test_contains_simulation_identity_fields(self, schema):
        result = schema.id_inputs()
        assert "simulator" in result
        assert "phantom" in result
        assert "random_seed" in result


# ---------------------------------------------------------------------------
# write() — ground truth only (minimal)
# ---------------------------------------------------------------------------


class TestWriteGroundTruth:
    def test_creates_ground_truth_group(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        assert "ground_truth" in h5file
        assert isinstance(h5file["ground_truth"], h5py.Group)

    def test_ground_truth_has_description(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        assert "description" in h5file["ground_truth"].attrs

    def test_activity_dataset_exists(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        assert "activity" in h5file["ground_truth"]
        assert h5file["ground_truth/activity"].dtype == np.float32

    def test_attenuation_dataset_exists(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        assert "attenuation" in h5file["ground_truth"]
        assert h5file["ground_truth/attenuation"].dtype == np.float32

    def test_activity_shape_matches(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        assert h5file["ground_truth/activity"].shape == (8, 16, 16)

    def test_attenuation_shape_matches(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        assert h5file["ground_truth/attenuation"].shape == (8, 16, 16)

    def test_ground_truth_data_roundtrip(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        np.testing.assert_array_equal(
            h5file["ground_truth/activity"][:],
            data["ground_truth"]["activity"],
        )
        np.testing.assert_array_equal(
            h5file["ground_truth/attenuation"][:],
            data["ground_truth"]["attenuation"],
        )

    def test_ground_truth_chunking(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        chunks = h5file["ground_truth/activity"].chunks
        assert chunks == (1, 16, 16)

    def test_ground_truth_compression(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        ds = h5file["ground_truth/activity"]
        assert ds.compression == "gzip"
        assert ds.compression_opts == 4

    def test_no_events_group_for_minimal(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        assert "events" not in h5file

    def test_no_metadata_group_for_minimal(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        assert "metadata" not in h5file

    def test_dataset_has_description_attr(self, schema, h5file):
        data = _minimal_ground_truth()
        schema.write(h5file, data)
        assert "description" in h5file["ground_truth/activity"].attrs
        assert "description" in h5file["ground_truth/attenuation"].attrs


# ---------------------------------------------------------------------------
# write() — events
# ---------------------------------------------------------------------------


class TestWriteEvents:
    def test_events_group_created(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        assert "events" in h5file
        assert isinstance(h5file["events"], h5py.Group)

    def test_events_group_has_description(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        assert "description" in h5file["events"].attrs

    def test_events_2p_dataset(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        ds = h5file["events/events_2p"]
        assert ds.shape == (100,)
        assert ds.dtype.names is not None

    def test_events_3p_dataset(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        ds = h5file["events/events_3p"]
        assert ds.shape == (50,)
        assert ds.dtype.names is not None

    def test_events_2p_data_roundtrip(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        stored = h5file["events/events_2p"][:]
        np.testing.assert_array_equal(
            stored["time"], data["events"]["events_2p"]["time"]
        )

    def test_events_dataset_has_description(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        assert "description" in h5file["events/events_2p"].attrs
        assert "description" in h5file["events/events_3p"].attrs


# ---------------------------------------------------------------------------
# write() — simulation metadata
# ---------------------------------------------------------------------------


class TestWriteSimulationMetadata:
    def test_metadata_simulation_group(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        assert "metadata" in h5file
        assert "simulation" in h5file["metadata"]

    def test_simulation_type_attr(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        grp = h5file["metadata/simulation"]
        assert grp.attrs["_type"] == "gate"

    def test_simulation_version_attr(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        grp = h5file["metadata/simulation"]
        assert grp.attrs["_version"] == 1

    def test_simulation_params(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        grp = h5file["metadata/simulation"]
        assert grp.attrs["gate_version"] == "9.3"
        assert grp.attrs["physics_list"] == "QGSP_BERT_HP_EMZ"
        assert grp.attrs["n_primaries"] == 1000000
        assert grp.attrs["random_seed"] == 12345

    def test_geometry_subgroup(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        grp = h5file["metadata/simulation/geometry"]
        assert grp.attrs["phantom"] == "XCAT"

    def test_source_subgroup(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        grp = h5file["metadata/simulation/source"]
        assert grp.attrs["activity_distribution"] == "uniform"
        assert grp.attrs["activities"] == "37.0 MBq"


# ---------------------------------------------------------------------------
# write() — full round-trip
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# write() — simulation metadata with pre-existing metadata group (sim.py:130)
# ---------------------------------------------------------------------------


class TestWriteSimulationMetadataExisting:
    def test_uses_existing_metadata_group(self, schema, h5file):
        """Covers sim.py:130 — metadata group already exists."""
        h5file.create_group("metadata")
        data = _full_sim_data()
        schema.write(h5file, data)
        assert "metadata/simulation" in h5file
        assert h5file["metadata/simulation"].attrs["_type"] == "gate"


# ---------------------------------------------------------------------------
# write() — full round-trip
# ---------------------------------------------------------------------------


class TestWriteFullRoundTrip:
    def test_all_groups_present(self, schema, h5file):
        data = _full_sim_data()
        schema.write(h5file, data)
        assert "ground_truth" in h5file
        assert "events" in h5file
        assert "metadata" in h5file


# ---------------------------------------------------------------------------
# Entry point registration
# ---------------------------------------------------------------------------


class TestEntryPointRegistration:
    def test_factory_returns_sim_schema(self):
        from fd5.imaging.sim import SimSchema

        instance = SimSchema()
        assert instance.product_type == "sim"


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_create_validate_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _minimal_ground_truth()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-sim"
            f.attrs["description"] = "Integration test sim file"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_generate_schema_for_sim(self, schema):
        register_schema("sim", schema)
        from fd5.schema import generate_schema

        result = generate_schema("sim")
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert result["properties"]["product"]["const"] == "sim"

    def test_full_data_validate_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _full_sim_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "full-sim-test"
            f.attrs["description"] = "Full sim round-trip test"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]
