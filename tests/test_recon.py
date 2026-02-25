"""Tests for fd5.imaging.recon — ReconSchema product schema."""

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
    from fd5.imaging.recon import ReconSchema

    return ReconSchema()


@pytest.fixture()
def h5file(tmp_path):
    path = tmp_path / "recon.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path):
    return tmp_path / "recon.h5"


def _make_volume_3d(shape=(64, 128, 128)):
    return np.random.default_rng(42).random(shape, dtype=np.float32)


def _make_volume_4d(shape=(4, 32, 64, 64)):
    return np.random.default_rng(42).random(shape, dtype=np.float32)


def _make_affine():
    aff = np.eye(4, dtype=np.float64)
    aff[0, 0] = 2.0  # 2mm voxel spacing Z
    aff[1, 1] = 1.0
    aff[2, 2] = 1.0
    return aff


def _minimal_3d_data():
    vol = _make_volume_3d((16, 32, 32))
    return {
        "volume": vol,
        "affine": _make_affine(),
        "dimension_order": "ZYX",
        "reference_frame": "LPS",
        "description": "Test static CT reconstruction volume",
    }


def _minimal_4d_data():
    vol = _make_volume_4d((3, 8, 16, 16))
    return {
        "volume": vol,
        "affine": _make_affine(),
        "dimension_order": "TZYX",
        "reference_frame": "LPS",
        "description": "Test dynamic PET reconstruction volume",
        "frames": {
            "n_frames": 3,
            "frame_type": "time",
            "description": "Dynamic time frames for PET reconstruction",
            "frame_start": np.array([0.0, 60.0, 120.0]),
            "frame_duration": np.array([60.0, 60.0, 60.0]),
            "frame_label": ["frame_0", "frame_1", "frame_2"],
        },
    }


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_product_schema_protocol(self, schema):
        assert isinstance(schema, ProductSchema)

    def test_product_type_is_recon(self, schema):
        assert schema.product_type == "recon"

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

    def test_product_const_is_recon(self, schema):
        result = schema.json_schema()
        assert result["properties"]["product"]["const"] == "recon"

    def test_requires_volume(self, schema):
        result = schema.json_schema()
        assert "volume" in result.get("required", []) or "volume" in result.get(
            "properties", {}
        )

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

    def test_contains_product_recon(self, schema):
        result = schema.required_root_attrs()
        assert result["product"] == "recon"

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
# write() — 3D static volume
# ---------------------------------------------------------------------------


class TestWrite3D:
    def test_writes_volume_dataset(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert "volume" in h5file
        assert h5file["volume"].dtype == np.float32

    def test_volume_shape_matches(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert h5file["volume"].shape == (16, 32, 32)

    def test_volume_has_affine_attr(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        aff = h5file["volume"].attrs["affine"]
        assert aff.shape == (4, 4)
        assert aff.dtype == np.float64

    def test_volume_has_dimension_order(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert h5file["volume"].attrs["dimension_order"] == "ZYX"

    def test_volume_has_reference_frame(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert h5file["volume"].attrs["reference_frame"] == "LPS"

    def test_volume_has_description(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert "description" in h5file["volume"].attrs

    def test_3d_chunking_strategy(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        chunks = h5file["volume"].chunks
        assert chunks == (1, 32, 32)

    def test_gzip_compression_level_4(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert h5file["volume"].compression == "gzip"
        assert h5file["volume"].compression_opts == 4

    def test_no_frames_group_for_3d(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert "frames" not in h5file


# ---------------------------------------------------------------------------
# write() — 4D dynamic volume
# ---------------------------------------------------------------------------


class TestWrite4D:
    def test_writes_volume_dataset(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        assert "volume" in h5file
        assert h5file["volume"].shape == (3, 8, 16, 16)

    def test_4d_chunking_strategy(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        chunks = h5file["volume"].chunks
        assert chunks == (1, 1, 16, 16)

    def test_4d_dimension_order(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        assert h5file["volume"].attrs["dimension_order"] == "TZYX"

    def test_frames_group_exists(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        assert "frames" in h5file
        assert isinstance(h5file["frames"], h5py.Group)

    def test_frames_attrs(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        grp = h5file["frames"]
        assert grp.attrs["n_frames"] == 3
        assert grp.attrs["frame_type"] == "time"
        assert "description" in grp.attrs

    def test_frame_start_dataset(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        ds = h5file["frames/frame_start"]
        np.testing.assert_array_almost_equal(ds[:], [0.0, 60.0, 120.0])

    def test_frame_duration_dataset(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        ds = h5file["frames/frame_duration"]
        np.testing.assert_array_almost_equal(ds[:], [60.0, 60.0, 60.0])

    def test_frame_label_dataset(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        ds = h5file["frames/frame_label"]
        labels = [v.decode() if isinstance(v, bytes) else str(v) for v in ds[:]]
        assert labels == ["frame_0", "frame_1", "frame_2"]


# ---------------------------------------------------------------------------
# write() — pyramid
# ---------------------------------------------------------------------------


class TestWritePyramid:
    def test_pyramid_group_created(self, schema, h5file):
        data = _minimal_3d_data()
        data["pyramid"] = {
            "scale_factors": [2, 4],
            "method": "local_mean",
        }
        schema.write(h5file, data)
        assert "pyramid" in h5file

    def test_pyramid_attrs(self, schema, h5file):
        data = _minimal_3d_data()
        data["pyramid"] = {
            "scale_factors": [2, 4],
            "method": "local_mean",
        }
        schema.write(h5file, data)
        grp = h5file["pyramid"]
        assert grp.attrs["n_levels"] == 2
        np.testing.assert_array_equal(grp.attrs["scale_factors"], [2, 4])
        assert grp.attrs["method"] == "local_mean"

    def test_pyramid_levels_created(self, schema, h5file):
        data = _minimal_3d_data()
        data["pyramid"] = {
            "scale_factors": [2, 4],
            "method": "local_mean",
        }
        schema.write(h5file, data)
        assert "pyramid/level_1" in h5file
        assert "pyramid/level_1/volume" in h5file
        assert "pyramid/level_2" in h5file
        assert "pyramid/level_2/volume" in h5file

    def test_pyramid_level_has_scale_factor_attr(self, schema, h5file):
        data = _minimal_3d_data()
        data["pyramid"] = {
            "scale_factors": [2],
            "method": "local_mean",
        }
        schema.write(h5file, data)
        ds = h5file["pyramid/level_1/volume"]
        assert ds.attrs["scale_factor"] == 2

    def test_pyramid_level_has_affine(self, schema, h5file):
        data = _minimal_3d_data()
        data["pyramid"] = {
            "scale_factors": [2],
            "method": "local_mean",
        }
        schema.write(h5file, data)
        ds = h5file["pyramid/level_1/volume"]
        assert "affine" in ds.attrs
        assert ds.attrs["affine"].shape == (4, 4)

    def test_pyramid_level_shape_downsampled(self, schema, h5file):
        data = _minimal_3d_data()
        data["pyramid"] = {
            "scale_factors": [2],
            "method": "local_mean",
        }
        schema.write(h5file, data)
        ds = h5file["pyramid/level_1/volume"]
        assert ds.shape == (8, 16, 16)

    def test_pyramid_level_compression(self, schema, h5file):
        data = _minimal_3d_data()
        data["pyramid"] = {
            "scale_factors": [2],
            "method": "local_mean",
        }
        schema.write(h5file, data)
        ds = h5file["pyramid/level_1/volume"]
        assert ds.compression == "gzip"
        assert ds.compression_opts == 4


# ---------------------------------------------------------------------------
# write() — MIP projections
# ---------------------------------------------------------------------------


class TestWriteMIP:
    def test_mip_coronal_created(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert "mip_coronal" in h5file

    def test_mip_sagittal_created(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert "mip_sagittal" in h5file

    def test_mip_coronal_shape(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        ds = h5file["mip_coronal"]
        assert ds.shape == (16, 32)

    def test_mip_sagittal_shape(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        ds = h5file["mip_sagittal"]
        assert ds.shape == (16, 32)

    def test_mip_coronal_attrs(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        ds = h5file["mip_coronal"]
        assert ds.attrs["projection_type"] == "mip"
        assert ds.attrs["axis"] == 1
        assert "description" in ds.attrs

    def test_mip_sagittal_attrs(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        ds = h5file["mip_sagittal"]
        assert ds.attrs["projection_type"] == "mip"
        assert ds.attrs["axis"] == 2
        assert "description" in ds.attrs

    def test_mip_dtype_float32(self, schema, h5file):
        data = _minimal_3d_data()
        schema.write(h5file, data)
        assert h5file["mip_coronal"].dtype == np.float32
        assert h5file["mip_sagittal"].dtype == np.float32

    def test_mip_4d_uses_summed_volume(self, schema, h5file):
        data = _minimal_4d_data()
        schema.write(h5file, data)
        vol = data["volume"]
        summed = vol.sum(axis=0)
        expected_coronal = summed.max(axis=1)
        np.testing.assert_array_almost_equal(h5file["mip_coronal"][:], expected_coronal)


# ---------------------------------------------------------------------------
# Entry point registration
# ---------------------------------------------------------------------------


class TestEntryPointRegistration:
    def test_factory_returns_recon_schema(self):
        from fd5.imaging.recon import ReconSchema

        instance = ReconSchema()
        assert instance.product_type == "recon"

    def test_entry_point_name_is_recon(self):
        """The entry point must register under name 'recon'."""
        import importlib.metadata

        eps = importlib.metadata.entry_points(group="fd5.schemas")
        names = [ep.name for ep in eps]
        assert "recon" in names


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_create_validate_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _minimal_3d_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-recon"
            f.attrs["description"] = "Integration test recon file"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_generate_schema_for_recon(self, schema):
        register_schema("recon", schema)
        from fd5.schema import generate_schema

        result = generate_schema("recon")
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert result["properties"]["product"]["const"] == "recon"
