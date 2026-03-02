"""Tests for fd5.imaging.transform — TransformSchema product schema."""

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
    from fd5.imaging.transform import TransformSchema

    return TransformSchema()


@pytest.fixture()
def h5file(tmp_path):
    path = tmp_path / "transform.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path):
    return tmp_path / "transform.h5"


def _make_affine():
    aff = np.eye(4, dtype=np.float64)
    aff[0, 3] = 10.0
    aff[1, 3] = -5.0
    aff[2, 3] = 3.0
    return aff


def _make_rigid_matrix():
    mat = np.eye(4, dtype=np.float64)
    theta = np.pi / 6
    mat[0, 0] = np.cos(theta)
    mat[0, 1] = -np.sin(theta)
    mat[1, 0] = np.sin(theta)
    mat[1, 1] = np.cos(theta)
    mat[0, 3] = 5.0
    mat[1, 3] = -3.0
    mat[2, 3] = 1.0
    return mat


def _make_displacement_field(shape=(8, 16, 16)):
    rng = np.random.default_rng(42)
    return rng.random((*shape, 3), dtype=np.float32) * 2.0 - 1.0


def _minimal_rigid_data():
    return {
        "transform_type": "rigid",
        "direction": "source_to_target",
        "matrix": _make_rigid_matrix(),
        "description": "Rigid PET-to-CT alignment",
    }


def _minimal_affine_data():
    return {
        "transform_type": "affine",
        "direction": "source_to_target",
        "matrix": _make_affine(),
        "description": "Affine cross-modality registration",
    }


def _minimal_deformable_data():
    field = _make_displacement_field((8, 16, 16))
    return {
        "transform_type": "deformable",
        "direction": "source_to_target",
        "displacement_field": {
            "data": field,
            "affine": np.eye(4, dtype=np.float64),
            "reference_frame": "LPS",
            "component_order": ["z", "y", "x"],
        },
        "description": "Deformable atlas registration",
    }


def _full_rigid_data():
    mat = _make_rigid_matrix()
    inv = np.linalg.inv(mat)
    return {
        "transform_type": "rigid",
        "direction": "source_to_target",
        "matrix": mat,
        "inverse_matrix": inv,
        "description": "Full rigid with inverse and metadata",
        "metadata": {
            "method": {
                "_type": "rigid",
                "_version": 1,
                "description": "Gradient descent MI registration",
                "optimizer": "gradient_descent",
                "metric": "mutual_information",
                "n_iterations": 200,
                "convergence": 1e-6,
            },
            "quality": {
                "metric_value": 0.85,
            },
        },
    }


def _full_deformable_data():
    field = _make_displacement_field((8, 16, 16))
    inv_field = -field
    return {
        "transform_type": "deformable",
        "direction": "target_to_source",
        "displacement_field": {
            "data": field,
            "affine": np.eye(4, dtype=np.float64),
            "reference_frame": "LPS",
            "component_order": ["z", "y", "x"],
        },
        "inverse_displacement_field": {
            "data": inv_field,
        },
        "description": "Full deformable with inverse, metadata, landmarks",
        "metadata": {
            "method": {
                "_type": "deformable",
                "_version": 1,
                "description": "LBFGS CC registration",
                "optimizer": "LBFGS",
                "metric": "cross_correlation",
                "regularization": "bending_energy",
                "regularization_weight": 1.0,
                "n_levels": 3,
                "grid_spacing": {
                    "value": [4.0, 4.0, 4.0],
                    "units": "mm",
                    "unitSI": 0.001,
                },
            },
            "quality": {
                "metric_value": 0.92,
                "jacobian_min": 0.3,
                "jacobian_max": 3.5,
                "tre": {"value": 1.2, "units": "mm", "unitSI": 0.001},
            },
        },
        "landmarks": {
            "source_points": np.array(
                [[10.0, 20.0, 30.0], [40.0, 50.0, 60.0]], dtype=np.float64
            ),
            "target_points": np.array(
                [[11.0, 21.0, 31.0], [41.0, 51.0, 61.0]], dtype=np.float64
            ),
            "labels": ["landmark_A", "landmark_B"],
        },
    }


def _landmark_only_data():
    mat = _make_rigid_matrix()
    return {
        "transform_type": "rigid",
        "direction": "source_to_target",
        "matrix": mat,
        "description": "Landmark-based registration",
        "metadata": {
            "method": {
                "_type": "manual_landmark",
                "n_landmarks": 3,
                "operator": "Dr. Smith",
            },
        },
        "landmarks": {
            "source_points": np.array(
                [[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.float64
            ),
            "target_points": np.array(
                [[1.1, 2.1, 3.1], [4.1, 5.1, 6.1], [7.1, 8.1, 9.1]],
                dtype=np.float64,
            ),
            "labels": ["L1", "L2", "L3"],
        },
    }


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_product_schema_protocol(self, schema):
        assert isinstance(schema, ProductSchema)

    def test_product_type_is_transform(self, schema):
        assert schema.product_type == "transform"

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

    def test_product_const_is_transform(self, schema):
        result = schema.json_schema()
        assert result["properties"]["product"]["const"] == "transform"

    def test_requires_transform_type(self, schema):
        result = schema.json_schema()
        assert "transform_type" in result["required"]

    def test_requires_direction(self, schema):
        result = schema.json_schema()
        assert "direction" in result["required"]

    def test_transform_type_enum(self, schema):
        result = schema.json_schema()
        enum = result["properties"]["transform_type"]["enum"]
        assert set(enum) == {"rigid", "affine", "deformable", "bspline"}

    def test_direction_enum(self, schema):
        result = schema.json_schema()
        enum = result["properties"]["direction"]["enum"]
        assert set(enum) == {"source_to_target", "target_to_source"}

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

    def test_contains_product_transform(self, schema):
        result = schema.required_root_attrs()
        assert result["product"] == "transform"

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

    def test_contains_expected_fields(self, schema):
        result = schema.id_inputs()
        assert "timestamp" in result
        assert "source_image_id" in result
        assert "target_image_id" in result


# ---------------------------------------------------------------------------
# write() — rigid matrix
# ---------------------------------------------------------------------------


class TestWriteRigid:
    def test_writes_matrix_dataset(self, schema, h5file):
        data = _minimal_rigid_data()
        schema.write(h5file, data)
        assert "matrix" in h5file
        assert h5file["matrix"].dtype == np.float64

    def test_matrix_shape(self, schema, h5file):
        data = _minimal_rigid_data()
        schema.write(h5file, data)
        assert h5file["matrix"].shape == (4, 4)

    def test_matrix_values_match(self, schema, h5file):
        data = _minimal_rigid_data()
        schema.write(h5file, data)
        np.testing.assert_array_almost_equal(h5file["matrix"][:], data["matrix"])

    def test_matrix_attrs(self, schema, h5file):
        data = _minimal_rigid_data()
        schema.write(h5file, data)
        ds = h5file["matrix"]
        assert "description" in ds.attrs
        assert ds.attrs["convention"] == "LPS"
        assert ds.attrs["units"] == "mm"

    def test_transform_type_attr(self, schema, h5file):
        data = _minimal_rigid_data()
        schema.write(h5file, data)
        assert h5file.attrs["transform_type"] == "rigid"

    def test_direction_attr(self, schema, h5file):
        data = _minimal_rigid_data()
        schema.write(h5file, data)
        assert h5file.attrs["direction"] == "source_to_target"

    def test_default_attr_is_matrix(self, schema, h5file):
        data = _minimal_rigid_data()
        schema.write(h5file, data)
        assert h5file.attrs["default"] == "matrix"

    def test_no_displacement_field(self, schema, h5file):
        data = _minimal_rigid_data()
        schema.write(h5file, data)
        assert "displacement_field" not in h5file


# ---------------------------------------------------------------------------
# write() — affine matrix
# ---------------------------------------------------------------------------


class TestWriteAffine:
    def test_writes_affine_matrix(self, schema, h5file):
        data = _minimal_affine_data()
        schema.write(h5file, data)
        assert "matrix" in h5file
        assert h5file.attrs["transform_type"] == "affine"

    def test_affine_matrix_values(self, schema, h5file):
        data = _minimal_affine_data()
        schema.write(h5file, data)
        np.testing.assert_array_almost_equal(h5file["matrix"][:], data["matrix"])


# ---------------------------------------------------------------------------
# write() — deformable displacement field
# ---------------------------------------------------------------------------


class TestWriteDeformable:
    def test_writes_displacement_field(self, schema, h5file):
        data = _minimal_deformable_data()
        schema.write(h5file, data)
        assert "displacement_field" in h5file

    def test_displacement_field_shape(self, schema, h5file):
        data = _minimal_deformable_data()
        schema.write(h5file, data)
        assert h5file["displacement_field"].shape == (8, 16, 16, 3)

    def test_displacement_field_dtype(self, schema, h5file):
        data = _minimal_deformable_data()
        schema.write(h5file, data)
        assert h5file["displacement_field"].dtype == np.float32

    def test_displacement_field_attrs(self, schema, h5file):
        data = _minimal_deformable_data()
        schema.write(h5file, data)
        ds = h5file["displacement_field"]
        assert ds.attrs["reference_frame"] == "LPS"
        assert list(ds.attrs["component_order"]) == ["z", "y", "x"]
        assert ds.attrs["affine"].shape == (4, 4)
        assert "description" in ds.attrs

    def test_displacement_field_compression(self, schema, h5file):
        data = _minimal_deformable_data()
        schema.write(h5file, data)
        ds = h5file["displacement_field"]
        assert ds.compression == "gzip"
        assert ds.compression_opts == 4

    def test_default_attr_is_displacement_field(self, schema, h5file):
        data = _minimal_deformable_data()
        schema.write(h5file, data)
        assert h5file.attrs["default"] == "displacement_field"

    def test_no_matrix_for_deformable_only(self, schema, h5file):
        data = _minimal_deformable_data()
        schema.write(h5file, data)
        assert "matrix" not in h5file

    def test_displacement_field_values_roundtrip(self, schema, h5file):
        data = _minimal_deformable_data()
        schema.write(h5file, data)
        expected = np.asarray(data["displacement_field"]["data"], dtype=np.float32)
        np.testing.assert_array_almost_equal(h5file["displacement_field"][:], expected)


# ---------------------------------------------------------------------------
# write() — inverse transforms
# ---------------------------------------------------------------------------


class TestWriteInverse:
    def test_inverse_matrix_written(self, schema, h5file):
        data = _full_rigid_data()
        schema.write(h5file, data)
        assert "inverse_matrix" in h5file
        assert h5file["inverse_matrix"].shape == (4, 4)

    def test_inverse_matrix_values(self, schema, h5file):
        data = _full_rigid_data()
        schema.write(h5file, data)
        np.testing.assert_array_almost_equal(
            h5file["inverse_matrix"][:], data["inverse_matrix"]
        )

    def test_inverse_matrix_attrs(self, schema, h5file):
        data = _full_rigid_data()
        schema.write(h5file, data)
        assert "description" in h5file["inverse_matrix"].attrs

    def test_inverse_displacement_field_written(self, schema, h5file):
        data = _full_deformable_data()
        schema.write(h5file, data)
        assert "inverse_displacement_field" in h5file
        assert h5file["inverse_displacement_field"].shape == (8, 16, 16, 3)

    def test_inverse_displacement_field_compression(self, schema, h5file):
        data = _full_deformable_data()
        schema.write(h5file, data)
        ds = h5file["inverse_displacement_field"]
        assert ds.compression == "gzip"


# ---------------------------------------------------------------------------
# write() — metadata
# ---------------------------------------------------------------------------


class TestWriteMetadata:
    def test_metadata_group_created(self, schema, h5file):
        data = _full_rigid_data()
        schema.write(h5file, data)
        assert "metadata" in h5file
        assert isinstance(h5file["metadata"], h5py.Group)

    def test_method_attrs(self, schema, h5file):
        data = _full_rigid_data()
        schema.write(h5file, data)
        method = h5file["metadata/method"]
        assert method.attrs["_type"] == "rigid"
        assert method.attrs["_version"] == 1
        assert method.attrs["optimizer"] == "gradient_descent"
        assert method.attrs["metric"] == "mutual_information"
        assert method.attrs["n_iterations"] == 200
        assert float(method.attrs["convergence"]) == pytest.approx(1e-6)

    def test_quality_attrs(self, schema, h5file):
        data = _full_rigid_data()
        schema.write(h5file, data)
        quality = h5file["metadata/quality"]
        assert "description" in quality.attrs
        assert float(quality.attrs["metric_value"]) == pytest.approx(0.85)

    def test_deformable_method_with_grid_spacing(self, schema, h5file):
        data = _full_deformable_data()
        schema.write(h5file, data)
        method = h5file["metadata/method"]
        assert method.attrs["_type"] == "deformable"
        assert method.attrs["regularization"] == "bending_energy"
        assert "grid_spacing" in method
        gs = method["grid_spacing"]
        np.testing.assert_array_almost_equal(gs.attrs["value"], [4.0, 4.0, 4.0])
        assert gs.attrs["units"] == "mm"

    def test_deformable_quality_jacobian(self, schema, h5file):
        data = _full_deformable_data()
        schema.write(h5file, data)
        quality = h5file["metadata/quality"]
        assert float(quality.attrs["jacobian_min"]) == pytest.approx(0.3)
        assert float(quality.attrs["jacobian_max"]) == pytest.approx(3.5)

    def test_deformable_quality_tre(self, schema, h5file):
        data = _full_deformable_data()
        schema.write(h5file, data)
        tre = h5file["metadata/quality/tre"]
        assert float(tre.attrs["value"]) == pytest.approx(1.2)
        assert tre.attrs["units"] == "mm"

    def test_manual_landmark_method(self, schema, h5file):
        data = _landmark_only_data()
        schema.write(h5file, data)
        method = h5file["metadata/method"]
        assert method.attrs["_type"] == "manual_landmark"
        assert method.attrs["n_landmarks"] == 3
        assert method.attrs["operator"] == "Dr. Smith"


# ---------------------------------------------------------------------------
# write() — landmarks
# ---------------------------------------------------------------------------


class TestWriteLandmarks:
    def test_landmarks_group_created(self, schema, h5file):
        data = _full_deformable_data()
        schema.write(h5file, data)
        assert "landmarks" in h5file

    def test_source_points(self, schema, h5file):
        data = _full_deformable_data()
        schema.write(h5file, data)
        ds = h5file["landmarks/source_points"]
        assert ds.shape == (2, 3)
        assert ds.dtype == np.float64
        np.testing.assert_array_almost_equal(ds[:], data["landmarks"]["source_points"])
        assert ds.attrs["units"] == "mm"

    def test_target_points(self, schema, h5file):
        data = _full_deformable_data()
        schema.write(h5file, data)
        ds = h5file["landmarks/target_points"]
        assert ds.shape == (2, 3)
        assert ds.dtype == np.float64
        np.testing.assert_array_almost_equal(ds[:], data["landmarks"]["target_points"])
        assert ds.attrs["units"] == "mm"

    def test_landmark_labels(self, schema, h5file):
        data = _full_deformable_data()
        schema.write(h5file, data)
        ds = h5file["landmarks/labels"]
        labels = [v.decode() if isinstance(v, bytes) else str(v) for v in ds[:]]
        assert labels == ["landmark_A", "landmark_B"]

    def test_landmarks_without_labels(self, schema, h5file):
        data = _minimal_rigid_data()
        data["landmarks"] = {
            "source_points": np.array([[1, 2, 3]], dtype=np.float64),
            "target_points": np.array([[4, 5, 6]], dtype=np.float64),
        }
        schema.write(h5file, data)
        assert "landmarks" in h5file
        assert "labels" not in h5file["landmarks"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_invalid_transform_type_raises(self, schema, h5file):
        data = _minimal_rigid_data()
        data["transform_type"] = "nonlinear"
        with pytest.raises(ValueError, match="Invalid transform_type"):
            schema.write(h5file, data)

    def test_invalid_direction_raises(self, schema, h5file):
        data = _minimal_rigid_data()
        data["direction"] = "left_to_right"
        with pytest.raises(ValueError, match="Invalid direction"):
            schema.write(h5file, data)


# ---------------------------------------------------------------------------
# Default override
# ---------------------------------------------------------------------------


class TestDefaultOverride:
    def test_explicit_default_overrides_auto(self, schema, h5file):
        data = _minimal_rigid_data()
        data["default"] = "displacement_field"
        schema.write(h5file, data)
        assert h5file.attrs["default"] == "displacement_field"


# ---------------------------------------------------------------------------
# Round-trip: write then read back
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_rigid_matrix_roundtrip(self, schema, h5path):
        data = _minimal_rigid_data()
        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            assert f.attrs["transform_type"] == "rigid"
            assert f.attrs["direction"] == "source_to_target"
            np.testing.assert_array_almost_equal(f["matrix"][:], data["matrix"])

    def test_deformable_field_roundtrip(self, schema, h5path):
        data = _minimal_deformable_data()
        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            assert f.attrs["transform_type"] == "deformable"
            expected = np.asarray(data["displacement_field"]["data"], dtype=np.float32)
            np.testing.assert_array_almost_equal(f["displacement_field"][:], expected)

    def test_full_rigid_roundtrip(self, schema, h5path):
        data = _full_rigid_data()
        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            np.testing.assert_array_almost_equal(f["matrix"][:], data["matrix"])
            np.testing.assert_array_almost_equal(
                f["inverse_matrix"][:], data["inverse_matrix"]
            )
            assert f["metadata/method"].attrs["_type"] == "rigid"

    def test_full_deformable_roundtrip(self, schema, h5path):
        data = _full_deformable_data()
        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            expected_field = np.asarray(
                data["displacement_field"]["data"], dtype=np.float32
            )
            np.testing.assert_array_almost_equal(
                f["displacement_field"][:], expected_field
            )
            assert f["metadata/method"].attrs["_type"] == "deformable"
            assert "landmarks" in f
            np.testing.assert_array_almost_equal(
                f["landmarks/source_points"][:],
                data["landmarks"]["source_points"],
            )


# ---------------------------------------------------------------------------
# Integration: embed schema + validate
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_create_validate_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _minimal_rigid_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-transform"
            f.attrs["description"] = data["description"]
            f.attrs["transform_type"] = data["transform_type"]
            f.attrs["direction"] = data["direction"]
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_generate_schema_for_transform(self, schema):
        register_schema("transform", schema)
        from fd5.schema import generate_schema

        result = generate_schema("transform")
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert result["properties"]["product"]["const"] == "transform"
