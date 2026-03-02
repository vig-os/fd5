"""Tests for fd5.imaging.roi — RoiSchema product schema."""

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
    from fd5.imaging.roi import RoiSchema

    return RoiSchema()


@pytest.fixture()
def h5file(tmp_path):
    path = tmp_path / "roi.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path):
    return tmp_path / "roi.h5"


def _make_affine():
    aff = np.eye(4, dtype=np.float64)
    aff[0, 0] = 2.0
    aff[1, 1] = 1.0
    aff[2, 2] = 1.0
    return aff


def _make_mask(shape=(16, 32, 32)):
    rng = np.random.default_rng(42)
    return rng.integers(0, 4, size=shape, dtype=np.int32)


def _minimal_mask_data():
    return {
        "mask": {
            "data": _make_mask(),
            "affine": _make_affine(),
            "reference_frame": "LPS",
            "description": "Test label mask",
        },
    }


def _minimal_regions_data():
    return {
        "regions": {
            "liver": {
                "label_value": 1,
                "color": [255, 0, 0],
                "description": "Liver region",
            },
            "kidney": {
                "label_value": 2,
                "color": [0, 255, 0],
                "description": "Kidney region",
                "anatomy": "kidney",
                "anatomy_vocabulary": "SNOMED CT",
                "anatomy_code": "64033007",
            },
        },
    }


def _minimal_geometry_data():
    return {
        "geometry": {
            "hot_sphere": {
                "shape": "sphere",
                "label_value": 1,
                "description": "Hot sphere for QC",
                "center": [10.0, 20.0, 30.0],
                "radius": 5.0,
            },
            "cold_box": {
                "shape": "box",
                "label_value": 2,
                "description": "Cold box region",
                "center": [0.0, 0.0, 0.0],
                "dimensions": [10.0, 20.0, 30.0],
            },
        },
    }


def _minimal_contours_data():
    return {
        "contours": {
            "description": "Per-slice contour coordinates (RT-STRUCT compatible)",
            "slice_0042": {
                "liver": {
                    "vertices": np.array(
                        [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]],
                        dtype=np.float32,
                    ),
                    "label_value": 1,
                },
            },
            "slice_0043": {
                "liver": {
                    "vertices": np.array(
                        [[7.0, 8.0], [9.0, 10.0]],
                        dtype=np.float32,
                    ),
                    "label_value": 1,
                },
            },
        },
    }


def _minimal_metadata_data():
    return {
        "metadata": {
            "method": {
                "_type": "manual",
                "_version": np.int64(1),
                "description": "Manual contouring",
                "tool": "MIM 7.2",
                "operator": "Dr. Smith",
            },
        },
    }


def _minimal_sources_data():
    return {
        "sources": {
            "reference_image": {
                "id": "abc123",
                "product": "recon",
                "file": "recon_abc123.h5",
                "content_hash": "sha256:deadbeef",
                "description": "Image on which these ROIs were defined",
            },
        },
    }


def _full_roi_data():
    data: dict = {}
    data.update(_minimal_mask_data())
    data.update(_minimal_regions_data())
    data.update(_minimal_geometry_data())
    data.update(_minimal_contours_data())
    data.update(_minimal_metadata_data())
    data.update(_minimal_sources_data())

    data["regions"]["liver"]["statistics"] = {
        "n_voxels": 1024,
        "computed_on": "abc123",
        "description": "ROI statistics",
        "volume": {"value": 12.5, "units": "mL", "unitSI": 1e-6},
        "mean": {"value": 3.2, "units": "SUV", "unitSI": 1.0},
        "max": {"value": 8.1, "units": "SUV", "unitSI": 1.0},
        "std": {"value": 1.4, "units": "SUV", "unitSI": 1.0},
    }
    return data


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_product_schema_protocol(self, schema):
        assert isinstance(schema, ProductSchema)

    def test_product_type_is_roi(self, schema):
        assert schema.product_type == "roi"

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

    def test_product_const_is_roi(self, schema):
        result = schema.json_schema()
        assert result["properties"]["product"]["const"] == "roi"

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

    def test_contains_product_roi(self, schema):
        result = schema.required_root_attrs()
        assert result["product"] == "roi"

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

    def test_contains_timestamp(self, schema):
        result = schema.id_inputs()
        assert "timestamp" in result


# ---------------------------------------------------------------------------
# write() — mask
# ---------------------------------------------------------------------------


class TestWriteMask:
    def test_writes_mask_dataset(self, schema, h5file):
        data = _minimal_mask_data()
        schema.write(h5file, data)
        assert "mask" in h5file
        assert h5file["mask"].dtype == np.int32

    def test_mask_shape_matches(self, schema, h5file):
        data = _minimal_mask_data()
        schema.write(h5file, data)
        assert h5file["mask"].shape == (16, 32, 32)

    def test_mask_has_affine_attr(self, schema, h5file):
        data = _minimal_mask_data()
        schema.write(h5file, data)
        aff = h5file["mask"].attrs["affine"]
        assert aff.shape == (4, 4)
        assert aff.dtype == np.float64

    def test_mask_has_reference_frame(self, schema, h5file):
        data = _minimal_mask_data()
        schema.write(h5file, data)
        assert h5file["mask"].attrs["reference_frame"] == "LPS"

    def test_mask_has_description(self, schema, h5file):
        data = _minimal_mask_data()
        schema.write(h5file, data)
        assert h5file["mask"].attrs["description"] == "Test label mask"

    def test_mask_gzip_compression(self, schema, h5file):
        data = _minimal_mask_data()
        schema.write(h5file, data)
        assert h5file["mask"].compression == "gzip"
        assert h5file["mask"].compression_opts == 4

    def test_mask_chunking(self, schema, h5file):
        data = _minimal_mask_data()
        schema.write(h5file, data)
        assert h5file["mask"].chunks == (1, 32, 32)

    def test_mask_data_roundtrip(self, schema, h5file):
        data = _minimal_mask_data()
        schema.write(h5file, data)
        np.testing.assert_array_equal(h5file["mask"][:], data["mask"]["data"])


# ---------------------------------------------------------------------------
# write() — regions
# ---------------------------------------------------------------------------


class TestWriteRegions:
    def test_regions_group_created(self, schema, h5file):
        data = _minimal_regions_data()
        schema.write(h5file, data)
        assert "regions" in h5file
        assert isinstance(h5file["regions"], h5py.Group)

    def test_region_has_label_value(self, schema, h5file):
        data = _minimal_regions_data()
        schema.write(h5file, data)
        assert h5file["regions/liver"].attrs["label_value"] == 1

    def test_region_has_color(self, schema, h5file):
        data = _minimal_regions_data()
        schema.write(h5file, data)
        np.testing.assert_array_equal(
            h5file["regions/liver"].attrs["color"],
            [255, 0, 0],
        )

    def test_region_has_description(self, schema, h5file):
        data = _minimal_regions_data()
        schema.write(h5file, data)
        assert h5file["regions/liver"].attrs["description"] == "Liver region"

    def test_region_optional_anatomy_attrs(self, schema, h5file):
        data = _minimal_regions_data()
        schema.write(h5file, data)
        kidney = h5file["regions/kidney"]
        assert kidney.attrs["anatomy"] == "kidney"
        assert kidney.attrs["anatomy_vocabulary"] == "SNOMED CT"
        assert kidney.attrs["anatomy_code"] == "64033007"

    def test_region_without_anatomy(self, schema, h5file):
        data = _minimal_regions_data()
        schema.write(h5file, data)
        liver = h5file["regions/liver"]
        assert "anatomy" not in liver.attrs


# ---------------------------------------------------------------------------
# write() — regions with statistics
# ---------------------------------------------------------------------------


class TestWriteRegionStatistics:
    def _data_with_stats(self):
        data = _minimal_regions_data()
        data["regions"]["liver"]["statistics"] = {
            "n_voxels": 1024,
            "computed_on": "abc123",
            "description": "ROI statistics",
            "volume": {"value": 12.5, "units": "mL", "unitSI": 1e-6},
            "mean": {"value": 3.2, "units": "SUV", "unitSI": 1.0},
        }
        return data

    def test_statistics_group_created(self, schema, h5file):
        data = self._data_with_stats()
        schema.write(h5file, data)
        assert "regions/liver/statistics" in h5file

    def test_statistics_n_voxels(self, schema, h5file):
        data = self._data_with_stats()
        schema.write(h5file, data)
        assert h5file["regions/liver/statistics"].attrs["n_voxels"] == 1024

    def test_statistics_computed_on(self, schema, h5file):
        data = self._data_with_stats()
        schema.write(h5file, data)
        assert h5file["regions/liver/statistics"].attrs["computed_on"] == "abc123"

    def test_statistics_volume_measure(self, schema, h5file):
        data = self._data_with_stats()
        schema.write(h5file, data)
        vol_grp = h5file["regions/liver/statistics/volume"]
        assert float(vol_grp.attrs["value"]) == pytest.approx(12.5)
        assert vol_grp.attrs["units"] == "mL"
        assert float(vol_grp.attrs["unitSI"]) == pytest.approx(1e-6)

    def test_statistics_mean_measure(self, schema, h5file):
        data = self._data_with_stats()
        schema.write(h5file, data)
        mean_grp = h5file["regions/liver/statistics/mean"]
        assert float(mean_grp.attrs["value"]) == pytest.approx(3.2)
        assert mean_grp.attrs["units"] == "SUV"

    def test_region_without_statistics(self, schema, h5file):
        data = _minimal_regions_data()
        schema.write(h5file, data)
        assert "regions/liver/statistics" not in h5file


# ---------------------------------------------------------------------------
# write() — geometry
# ---------------------------------------------------------------------------


class TestWriteGeometry:
    def test_geometry_group_created(self, schema, h5file):
        data = _minimal_geometry_data()
        schema.write(h5file, data)
        assert "geometry" in h5file

    def test_sphere_shape_attrs(self, schema, h5file):
        data = _minimal_geometry_data()
        schema.write(h5file, data)
        grp = h5file["geometry/hot_sphere"]
        assert grp.attrs["shape"] == "sphere"
        assert grp.attrs["label_value"] == 1
        assert grp.attrs["description"] == "Hot sphere for QC"

    def test_sphere_center(self, schema, h5file):
        data = _minimal_geometry_data()
        schema.write(h5file, data)
        center = h5file["geometry/hot_sphere/center"]
        np.testing.assert_array_almost_equal(
            center.attrs["value"],
            [10.0, 20.0, 30.0],
        )
        assert center.attrs["units"] == "mm"
        assert float(center.attrs["unitSI"]) == pytest.approx(0.001)

    def test_sphere_radius(self, schema, h5file):
        data = _minimal_geometry_data()
        schema.write(h5file, data)
        radius = h5file["geometry/hot_sphere/radius"]
        assert float(radius.attrs["value"]) == pytest.approx(5.0)
        assert radius.attrs["units"] == "mm"

    def test_box_dimensions(self, schema, h5file):
        data = _minimal_geometry_data()
        schema.write(h5file, data)
        dims = h5file["geometry/cold_box/dimensions"]
        np.testing.assert_array_almost_equal(
            dims.attrs["value"],
            [10.0, 20.0, 30.0],
        )
        assert dims.attrs["units"] == "mm"

    def test_box_no_radius(self, schema, h5file):
        data = _minimal_geometry_data()
        schema.write(h5file, data)
        assert "geometry/cold_box/radius" not in h5file


# ---------------------------------------------------------------------------
# write() — contours
# ---------------------------------------------------------------------------


class TestWriteContours:
    def test_contours_group_created(self, schema, h5file):
        data = _minimal_contours_data()
        schema.write(h5file, data)
        assert "contours" in h5file

    def test_contours_description(self, schema, h5file):
        data = _minimal_contours_data()
        schema.write(h5file, data)
        assert "description" in h5file["contours"].attrs

    def test_slice_group_created(self, schema, h5file):
        data = _minimal_contours_data()
        schema.write(h5file, data)
        assert "contours/slice_0042" in h5file
        assert "contours/slice_0043" in h5file

    def test_contour_dataset_shape(self, schema, h5file):
        data = _minimal_contours_data()
        schema.write(h5file, data)
        ds = h5file["contours/slice_0042/liver"]
        assert ds.shape == (3, 2)
        assert ds.dtype == np.float32

    def test_contour_dataset_attrs(self, schema, h5file):
        data = _minimal_contours_data()
        schema.write(h5file, data)
        ds = h5file["contours/slice_0042/liver"]
        assert ds.attrs["units"] == "mm"
        assert ds.attrs["label_value"] == 1

    def test_contour_data_roundtrip(self, schema, h5file):
        data = _minimal_contours_data()
        schema.write(h5file, data)
        ds = h5file["contours/slice_0042/liver"]
        expected = data["contours"]["slice_0042"]["liver"]["vertices"]
        np.testing.assert_array_almost_equal(ds[:], expected)


# ---------------------------------------------------------------------------
# write() — metadata
# ---------------------------------------------------------------------------


class TestWriteMetadata:
    def test_metadata_group_created(self, schema, h5file):
        data = _minimal_metadata_data()
        schema.write(h5file, data)
        assert "metadata" in h5file

    def test_method_type(self, schema, h5file):
        data = _minimal_metadata_data()
        schema.write(h5file, data)
        assert h5file["metadata/method"].attrs["_type"] == "manual"

    def test_method_version(self, schema, h5file):
        data = _minimal_metadata_data()
        schema.write(h5file, data)
        assert h5file["metadata/method"].attrs["_version"] == 1

    def test_method_tool(self, schema, h5file):
        data = _minimal_metadata_data()
        schema.write(h5file, data)
        assert h5file["metadata/method"].attrs["tool"] == "MIM 7.2"

    def test_method_operator(self, schema, h5file):
        data = _minimal_metadata_data()
        schema.write(h5file, data)
        assert h5file["metadata/method"].attrs["operator"] == "Dr. Smith"

    def test_ai_segmentation_method(self, schema, h5file):
        data = {
            "metadata": {
                "method": {
                    "_type": "ai_segmentation",
                    "_version": np.int64(1),
                    "description": "AI segmentation",
                    "model": "TotalSegmentator",
                    "model_version": "2.0.1",
                    "weights_hash": "sha256:abc",
                    "task": "total",
                },
            },
        }
        schema.write(h5file, data)
        m = h5file["metadata/method"]
        assert m.attrs["_type"] == "ai_segmentation"
        assert m.attrs["model"] == "TotalSegmentator"


# ---------------------------------------------------------------------------
# write() — sources
# ---------------------------------------------------------------------------


class TestWriteSources:
    def test_sources_group_created(self, schema, h5file):
        data = _minimal_sources_data()
        schema.write(h5file, data)
        assert "sources" in h5file

    def test_reference_image_attrs(self, schema, h5file):
        data = _minimal_sources_data()
        schema.write(h5file, data)
        ref = h5file["sources/reference_image"]
        assert ref.attrs["id"] == "abc123"
        assert ref.attrs["product"] == "recon"
        assert ref.attrs["role"] == "reference_image"
        assert "description" in ref.attrs

    def test_reference_image_file(self, schema, h5file):
        data = _minimal_sources_data()
        schema.write(h5file, data)
        ref = h5file["sources/reference_image"]
        assert ref.attrs["file"] == "recon_abc123.h5"
        assert ref.attrs["content_hash"] == "sha256:deadbeef"


# ---------------------------------------------------------------------------
# write() — full ROI (all representations)
# ---------------------------------------------------------------------------


class TestWriteFullRoi:
    def test_all_groups_present(self, schema, h5file):
        data = _full_roi_data()
        schema.write(h5file, data)
        assert "mask" in h5file
        assert "regions" in h5file
        assert "geometry" in h5file
        assert "contours" in h5file
        assert "metadata" in h5file
        assert "sources" in h5file

    def test_full_roundtrip_mask(self, schema, h5file):
        data = _full_roi_data()
        schema.write(h5file, data)
        np.testing.assert_array_equal(
            h5file["mask"][:],
            data["mask"]["data"],
        )

    def test_full_roundtrip_statistics(self, schema, h5file):
        data = _full_roi_data()
        schema.write(h5file, data)
        stat_grp = h5file["regions/liver/statistics"]
        assert stat_grp.attrs["n_voxels"] == 1024
        vol = h5file["regions/liver/statistics/volume"]
        assert float(vol.attrs["value"]) == pytest.approx(12.5)
        max_grp = h5file["regions/liver/statistics/max"]
        assert float(max_grp.attrs["value"]) == pytest.approx(8.1)
        std_grp = h5file["regions/liver/statistics/std"]
        assert float(std_grp.attrs["value"]) == pytest.approx(1.4)


# ---------------------------------------------------------------------------
# write() — empty / minimal cases
# ---------------------------------------------------------------------------


class TestWriteEdgeCases:
    def test_write_with_no_data_succeeds(self, schema, h5file):
        schema.write(h5file, {})

    def test_mask_only(self, schema, h5file):
        data = _minimal_mask_data()
        schema.write(h5file, data)
        assert "mask" in h5file
        assert "regions" not in h5file
        assert "geometry" not in h5file
        assert "contours" not in h5file

    def test_geometry_only(self, schema, h5file):
        data = _minimal_geometry_data()
        schema.write(h5file, data)
        assert "geometry" in h5file
        assert "mask" not in h5file

    def test_contours_only(self, schema, h5file):
        data = _minimal_contours_data()
        schema.write(h5file, data)
        assert "contours" in h5file
        assert "mask" not in h5file

    def test_mask_default_description(self, schema, h5file):
        data = {
            "mask": {
                "data": _make_mask(),
                "affine": _make_affine(),
                "reference_frame": "LPS",
            },
        }
        schema.write(h5file, data)
        assert h5file["mask"].attrs["description"] == (
            "Label mask where each integer maps to a named region"
        )

    def test_idempotent_write(self, schema, tmp_path):
        """Writing identical data twice to separate files produces the same structure."""
        data = _minimal_mask_data()
        p1 = tmp_path / "a.h5"
        p2 = tmp_path / "b.h5"
        with h5py.File(p1, "w") as f:
            schema.write(f, data)
        with h5py.File(p2, "w") as f:
            schema.write(f, data)
        with h5py.File(p1, "r") as f1, h5py.File(p2, "r") as f2:
            np.testing.assert_array_equal(f1["mask"][:], f2["mask"][:])
            assert (
                f1["mask"].attrs["reference_frame"]
                == f2["mask"].attrs["reference_frame"]
            )


# ---------------------------------------------------------------------------
# Integration: embed_schema + validate round-trip
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_create_validate_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _full_roi_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-roi"
            f.attrs["description"] = "Integration test ROI file"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_generate_schema_for_roi(self, schema):
        register_schema("roi", schema)
        from fd5.schema import generate_schema

        result = generate_schema("roi")
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert result["properties"]["product"]["const"] == "roi"
