"""Tests for fd5.imaging.sinogram — SinogramSchema product schema."""

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
    from fd5.imaging.sinogram import SinogramSchema

    return SinogramSchema()


@pytest.fixture()
def h5file(tmp_path):
    path = tmp_path / "sinogram.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path):
    return tmp_path / "sinogram.h5"


def _make_sinogram_3d(shape=(11, 180, 128)):
    return np.random.default_rng(42).random(shape, dtype=np.float32)


def _make_sinogram_4d(shape=(11, 13, 180, 128)):
    return np.random.default_rng(42).random(shape, dtype=np.float32)


def _minimal_3d_data():
    sino = _make_sinogram_3d((11, 180, 128))
    return {
        "sinogram": sino,
        "n_radial": 128,
        "n_angular": 180,
        "n_planes": 11,
        "span": 3,
        "max_ring_diff": 5,
        "tof_bins": 0,
    }


def _minimal_4d_data():
    sino = _make_sinogram_4d((11, 13, 180, 128))
    return {
        "sinogram": sino,
        "n_radial": 128,
        "n_angular": 180,
        "n_planes": 11,
        "span": 3,
        "max_ring_diff": 5,
        "tof_bins": 13,
    }


def _full_data():
    data = _minimal_3d_data()
    data["acquisition"] = {
        "n_rings": 64,
        "n_crystals_per_ring": 504,
        "ring_spacing": 4.0,
        "crystal_pitch": 2.0,
    }
    data["corrections_applied"] = {
        "normalization": True,
        "attenuation": True,
        "scatter": False,
        "randoms": True,
        "dead_time": False,
        "decay": True,
    }
    data["additive_correction"] = np.zeros((11, 180, 128), dtype=np.float32)
    data["multiplicative_correction"] = np.ones((11, 180, 128), dtype=np.float32)
    return data


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_product_schema_protocol(self, schema):
        assert isinstance(schema, ProductSchema)

    def test_product_type_is_sinogram(self, schema):
        assert schema.product_type == "sinogram"

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

    def test_product_const_is_sinogram(self, schema):
        result = schema.json_schema()
        assert result["properties"]["product"]["const"] == "sinogram"

    def test_requires_sinogram_fields(self, schema):
        result = schema.json_schema()
        required = result["required"]
        for field in [
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
        ]:
            assert field in required

    def test_sinogram_geometry_properties(self, schema):
        result = schema.json_schema()
        props = result["properties"]
        for field in [
            "n_radial",
            "n_angular",
            "n_planes",
            "span",
            "max_ring_diff",
            "tof_bins",
        ]:
            assert field in props
            assert props[field]["type"] == "integer"

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

    def test_contains_product_sinogram(self, schema):
        result = schema.required_root_attrs()
        assert result["product"] == "sinogram"

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


# ---------------------------------------------------------------------------
# write() — 3D non-TOF sinogram
# ---------------------------------------------------------------------------


class TestWrite3D:
    def test_writes_sinogram_dataset(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert "sinogram" in h5file
        assert h5file["sinogram"].dtype == np.float32

    def test_sinogram_shape_matches(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert h5file["sinogram"].shape == (11, 180, 128)

    def test_sinogram_has_description(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert (
            h5file["sinogram"].attrs["description"]
            == "Projection data in sinogram format"
        )

    def test_3d_chunking_strategy(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        chunks = h5file["sinogram"].chunks
        assert chunks == (1, 180, 128)

    def test_gzip_compression_level_4(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert h5file["sinogram"].compression == "gzip"
        assert h5file["sinogram"].compression_opts == 4

    def test_root_attrs_written(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert h5file.attrs["n_radial"] == 128
        assert h5file.attrs["n_angular"] == 180
        assert h5file.attrs["n_planes"] == 11
        assert h5file.attrs["span"] == 3
        assert h5file.attrs["max_ring_diff"] == 5
        assert h5file.attrs["tof_bins"] == 0

    def test_metadata_group_exists(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert "metadata" in h5file

    def test_data_round_trip(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        np.testing.assert_array_equal(h5file["sinogram"][:], data["sinogram"])


# ---------------------------------------------------------------------------
# write() — 4D TOF sinogram
# ---------------------------------------------------------------------------


class TestWrite4D:
    def test_writes_sinogram_dataset(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        assert "sinogram" in h5file
        assert h5file["sinogram"].shape == (11, 13, 180, 128)

    def test_4d_chunking_strategy(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        chunks = h5file["sinogram"].chunks
        assert chunks == (1, 1, 180, 128)

    def test_tof_bins_in_root_attrs(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        assert h5file.attrs["tof_bins"] == 13

    def test_4d_data_round_trip(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        np.testing.assert_array_equal(h5file["sinogram"][:], data["sinogram"])


# ---------------------------------------------------------------------------
# write() — acquisition metadata
# ---------------------------------------------------------------------------


class TestWriteAcquisition:
    def test_acquisition_group_created(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        assert "metadata/acquisition" in h5file

    def test_acquisition_attrs(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        grp = h5file["metadata/acquisition"]
        assert grp.attrs["n_rings"] == 64
        assert grp.attrs["n_crystals_per_ring"] == 504
        assert grp.attrs["description"] == "Scanner geometry"

    def test_ring_spacing(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        grp = h5file["metadata/acquisition/ring_spacing"]
        assert float(grp.attrs["value"]) == 4.0
        assert grp.attrs["units"] == "mm"
        assert float(grp.attrs["unitSI"]) == 0.001

    def test_crystal_pitch(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        grp = h5file["metadata/acquisition/crystal_pitch"]
        assert float(grp.attrs["value"]) == 2.0
        assert grp.attrs["units"] == "mm"
        assert float(grp.attrs["unitSI"]) == 0.001


# ---------------------------------------------------------------------------
# write() — corrections_applied metadata
# ---------------------------------------------------------------------------


class TestWriteCorrections:
    def test_corrections_group_created(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        assert "metadata/corrections_applied" in h5file

    def test_corrections_flags(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        grp = h5file["metadata/corrections_applied"]
        assert bool(grp.attrs["normalization"]) is True
        assert bool(grp.attrs["attenuation"]) is True
        assert bool(grp.attrs["scatter"]) is False
        assert bool(grp.attrs["randoms"]) is True
        assert bool(grp.attrs["dead_time"]) is False
        assert bool(grp.attrs["decay"]) is True

    def test_corrections_description(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        grp = h5file["metadata/corrections_applied"]
        assert (
            grp.attrs["description"]
            == "Which corrections have been applied to this sinogram"
        )


# ---------------------------------------------------------------------------
# write() — additive/multiplicative correction datasets
# ---------------------------------------------------------------------------


class TestWriteCorrectionDatasets:
    def test_additive_correction_written(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        assert "additive_correction" in h5file
        assert h5file["additive_correction"].dtype == np.float32
        assert h5file["additive_correction"].shape == (11, 180, 128)

    def test_additive_correction_description(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        ds = h5file["additive_correction"]
        assert ds.attrs["description"] == "Additive correction term (scatter + randoms)"

    def test_additive_correction_compressed(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        ds = h5file["additive_correction"]
        assert ds.compression == "gzip"
        assert ds.compression_opts == 4

    def test_multiplicative_correction_written(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        assert "multiplicative_correction" in h5file
        assert h5file["multiplicative_correction"].dtype == np.float32
        assert h5file["multiplicative_correction"].shape == (11, 180, 128)

    def test_multiplicative_correction_description(self, schema, h5file):
        data = _full_data()
        schema.write(h5file, data)
        ds = h5file["multiplicative_correction"]
        assert ds.attrs["description"] == (
            "Multiplicative correction term (normalization * attenuation)"
        )

    def test_no_corrections_when_absent(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert "additive_correction" not in h5file
        assert "multiplicative_correction" not in h5file


# ---------------------------------------------------------------------------
# Entry point registration
# ---------------------------------------------------------------------------


class TestEntryPointRegistration:
    def test_factory_returns_sinogram_schema(self):
        from fd5.imaging.sinogram import SinogramSchema

        instance = SinogramSchema()
        assert instance.product_type == "sinogram"

    def test_register_schema_lookup(self):
        from fd5.imaging.sinogram import SinogramSchema
        from fd5.registry import get_schema

        register_schema("sinogram", SinogramSchema())
        result = get_schema("sinogram")
        assert result.product_type == "sinogram"


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_create_validate_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _full_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-sinogram"
            f.attrs["description"] = "Integration test sinogram file"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_generate_schema_for_sinogram(self, schema):
        register_schema("sinogram", schema)
        from fd5.schema import generate_schema

        result = generate_schema("sinogram")
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert result["properties"]["product"]["const"] == "sinogram"
