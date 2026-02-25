"""Tests for fd5.imaging.spectrum — SpectrumSchema product schema."""

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
    from fd5.imaging.spectrum import SpectrumSchema

    return SpectrumSchema()


@pytest.fixture()
def h5file(tmp_path):
    path = tmp_path / "spectrum.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path):
    return tmp_path / "spectrum.h5"


def _make_1d_energy_spectrum(n_bins=256):
    rng = np.random.default_rng(42)
    counts = rng.poisson(100, size=n_bins).astype(np.float32)
    bin_edges = np.linspace(0, 1500, n_bins + 1)
    return counts, bin_edges


def _make_2d_coincidence(n_bins_0=64, n_bins_1=64):
    rng = np.random.default_rng(42)
    counts = rng.poisson(10, size=(n_bins_0, n_bins_1)).astype(np.float32)
    bin_edges_0 = np.linspace(0, 1500, n_bins_0 + 1)
    bin_edges_1 = np.linspace(0, 1500, n_bins_1 + 1)
    return counts, bin_edges_0, bin_edges_1


def _minimal_1d_data():
    counts, bin_edges = _make_1d_energy_spectrum(128)
    return {
        "counts": counts,
        "axes": [
            {
                "label": "energy",
                "units": "keV",
                "unitSI": 1.602e-16,
                "bin_edges": bin_edges,
                "description": "Photon energy",
            },
        ],
    }


def _minimal_2d_data():
    counts, edges_0, edges_1 = _make_2d_coincidence(32, 32)
    return {
        "counts": counts,
        "axes": [
            {
                "label": "energy_1",
                "units": "keV",
                "unitSI": 1.602e-16,
                "bin_edges": edges_0,
                "description": "Energy detector 1",
            },
            {
                "label": "energy_2",
                "units": "keV",
                "unitSI": 1.602e-16,
                "bin_edges": edges_1,
                "description": "Energy detector 2",
            },
        ],
    }


def _1d_with_errors():
    data = _minimal_1d_data()
    data["counts_errors"] = np.sqrt(data["counts"])
    return data


def _1d_with_metadata():
    data = _minimal_1d_data()
    data["metadata"] = {
        "method": {
            "_type": "energy",
            "_version": 1,
            "description": "Energy spectrum from HPGe detector",
            "detector": "HPGe",
            "energy_range": {
                "value": [0, 1500],
                "units": "keV",
                "unitSI": 1.602e-16,
            },
        },
        "acquisition": {
            "total_counts": 1000000,
            "dead_time_fraction": 0.05,
            "description": "Acquisition statistics",
            "live_time": {"value": 3600.0, "units": "s", "unitSI": 1.0},
            "real_time": {"value": 3789.47, "units": "s", "unitSI": 1.0},
        },
    }
    return data


def _1d_with_fit():
    counts, bin_edges = _make_1d_energy_spectrum(128)
    rng = np.random.default_rng(99)
    curve = counts + rng.normal(0, 2, size=counts.shape).astype(np.float32)
    residuals = counts - curve
    comp_curve = curve * 0.7
    return {
        "counts": counts,
        "axes": [
            {
                "label": "time",
                "units": "ns",
                "unitSI": 1e-9,
                "bin_edges": np.linspace(0, 50, 129),
                "description": "Positron lifetime",
            },
        ],
        "fit": {
            "_type": "multi_exponential",
            "_version": 1,
            "chi_squared": 1.02,
            "degrees_of_freedom": 125,
            "description": "PALS multi-exponential fit",
            "curve": curve,
            "residuals": residuals,
            "components": [
                {
                    "label": "free positron",
                    "intensity": 0.72,
                    "intensity_error": 0.02,
                    "description": "Free positron annihilation component",
                    "lifetime": {"value": 0.382, "units": "ns", "unitSI": 1e-9},
                    "lifetime_error": {"value": 0.005, "units": "ns", "unitSI": 1e-9},
                    "curve": comp_curve,
                },
                {
                    "label": "positronium",
                    "intensity": 0.28,
                    "description": "Ortho-positronium component",
                    "lifetime": {"value": 1.85, "units": "ns", "unitSI": 1e-9},
                },
            ],
            "parameters": {
                "names": ["tau_1", "I_1", "tau_2", "I_2", "bg"],
                "values": [0.382, 0.72, 1.85, 0.28, 12.5],
                "errors": [0.005, 0.02, 0.03, 0.02, 0.8],
                "description": "All fit parameters as arrays",
            },
        },
    }


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_product_schema_protocol(self, schema):
        assert isinstance(schema, ProductSchema)

    def test_product_type_is_spectrum(self, schema):
        assert schema.product_type == "spectrum"

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

    def test_product_const_is_spectrum(self, schema):
        result = schema.json_schema()
        assert result["properties"]["product"]["const"] == "spectrum"

    def test_has_n_dimensions_property(self, schema):
        result = schema.json_schema()
        assert "n_dimensions" in result["properties"]

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

    def test_contains_product_spectrum(self, schema):
        result = schema.required_root_attrs()
        assert result["product"] == "spectrum"

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

    def test_returns_fresh_list(self, schema):
        a = schema.id_inputs()
        b = schema.id_inputs()
        assert a is not b


# ---------------------------------------------------------------------------
# write() — 1D energy spectrum
# ---------------------------------------------------------------------------


class TestWrite1D:
    def test_writes_counts_dataset(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        assert "counts" in h5file
        assert h5file["counts"].dtype == np.float32

    def test_counts_shape_matches(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        assert h5file["counts"].shape == (128,)

    def test_counts_has_description(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        assert "description" in h5file["counts"].attrs

    def test_counts_gzip_compressed(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        assert h5file["counts"].compression == "gzip"
        assert h5file["counts"].compression_opts == 4

    def test_n_dimensions_attr(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        assert h5file.attrs["n_dimensions"] == 1

    def test_default_attr(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        assert h5file.attrs["default"] == "counts"

    def test_axes_group_created(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        assert "axes" in h5file
        assert "axes/ax0" in h5file

    def test_ax0_attrs(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        ax0 = h5file["axes/ax0"]
        assert ax0.attrs["label"] == "energy"
        assert ax0.attrs["units"] == "keV"
        assert ax0.attrs["unitSI"] == pytest.approx(1.602e-16)
        assert "description" in ax0.attrs

    def test_bin_edges_dataset(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        edges = h5file["axes/ax0/bin_edges"][:]
        assert edges.dtype == np.float64
        assert edges.shape == (129,)

    def test_bin_centers_dataset(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        centers = h5file["axes/ax0/bin_centers"][:]
        assert centers.dtype == np.float64
        assert centers.shape == (128,)

    def test_bin_centers_are_midpoints(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        edges = h5file["axes/ax0/bin_edges"][:]
        centers = h5file["axes/ax0/bin_centers"][:]
        expected = 0.5 * (edges[:-1] + edges[1:])
        np.testing.assert_array_almost_equal(centers, expected)

    def test_no_fit_group_when_absent(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        assert "fit" not in h5file

    def test_no_metadata_group_when_absent(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        assert "metadata" not in h5file

    def test_no_counts_errors_when_absent(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        assert "counts_errors" not in h5file

    def test_roundtrip_counts_data(self, schema, h5file):
        data = _minimal_1d_data()
        schema.write(h5file, data)
        np.testing.assert_array_almost_equal(h5file["counts"][:], data["counts"])


# ---------------------------------------------------------------------------
# write() — 2D coincidence matrix
# ---------------------------------------------------------------------------


class TestWrite2D:
    def test_writes_counts_dataset(self, schema, h5file):
        data = _minimal_2d_data()
        schema.write(h5file, data)
        assert "counts" in h5file
        assert h5file["counts"].shape == (32, 32)

    def test_n_dimensions_attr(self, schema, h5file):
        data = _minimal_2d_data()
        schema.write(h5file, data)
        assert h5file.attrs["n_dimensions"] == 2

    def test_both_axes_exist(self, schema, h5file):
        data = _minimal_2d_data()
        schema.write(h5file, data)
        assert "axes/ax0" in h5file
        assert "axes/ax1" in h5file

    def test_ax1_bin_edges_shape(self, schema, h5file):
        data = _minimal_2d_data()
        schema.write(h5file, data)
        edges = h5file["axes/ax1/bin_edges"][:]
        assert edges.shape == (33,)

    def test_ax1_attrs(self, schema, h5file):
        data = _minimal_2d_data()
        schema.write(h5file, data)
        ax1 = h5file["axes/ax1"]
        assert ax1.attrs["label"] == "energy_2"
        assert ax1.attrs["units"] == "keV"


# ---------------------------------------------------------------------------
# write() — counts_errors
# ---------------------------------------------------------------------------


class TestWriteCountsErrors:
    def test_errors_dataset_created(self, schema, h5file):
        data = _1d_with_errors()
        schema.write(h5file, data)
        assert "counts_errors" in h5file

    def test_errors_shape_matches_counts(self, schema, h5file):
        data = _1d_with_errors()
        schema.write(h5file, data)
        assert h5file["counts_errors"].shape == h5file["counts"].shape

    def test_errors_dtype_float32(self, schema, h5file):
        data = _1d_with_errors()
        schema.write(h5file, data)
        assert h5file["counts_errors"].dtype == np.float32

    def test_errors_gzip_compressed(self, schema, h5file):
        data = _1d_with_errors()
        schema.write(h5file, data)
        assert h5file["counts_errors"].compression == "gzip"

    def test_errors_has_description(self, schema, h5file):
        data = _1d_with_errors()
        schema.write(h5file, data)
        assert "description" in h5file["counts_errors"].attrs


# ---------------------------------------------------------------------------
# write() — metadata
# ---------------------------------------------------------------------------


class TestWriteMetadata:
    def test_metadata_group_created(self, schema, h5file):
        data = _1d_with_metadata()
        schema.write(h5file, data)
        assert "metadata" in h5file

    def test_method_group(self, schema, h5file):
        data = _1d_with_metadata()
        schema.write(h5file, data)
        method = h5file["metadata/method"]
        assert method.attrs["_type"] == "energy"
        assert method.attrs["_version"] == 1
        assert "description" in method.attrs

    def test_method_extra_attrs(self, schema, h5file):
        data = _1d_with_metadata()
        schema.write(h5file, data)
        method = h5file["metadata/method"]
        assert method.attrs["detector"] == "HPGe"

    def test_method_subgroup(self, schema, h5file):
        data = _1d_with_metadata()
        schema.write(h5file, data)
        er = h5file["metadata/method/energy_range"]
        np.testing.assert_array_almost_equal(er.attrs["value"], [0, 1500])
        assert er.attrs["units"] == "keV"

    def test_acquisition_group(self, schema, h5file):
        data = _1d_with_metadata()
        schema.write(h5file, data)
        acq = h5file["metadata/acquisition"]
        assert acq.attrs["total_counts"] == 1000000
        assert acq.attrs["dead_time_fraction"] == pytest.approx(0.05)

    def test_acquisition_live_time(self, schema, h5file):
        data = _1d_with_metadata()
        schema.write(h5file, data)
        lt = h5file["metadata/acquisition/live_time"]
        assert lt.attrs["value"] == pytest.approx(3600.0)
        assert lt.attrs["units"] == "s"
        assert lt.attrs["unitSI"] == pytest.approx(1.0)

    def test_acquisition_real_time(self, schema, h5file):
        data = _1d_with_metadata()
        schema.write(h5file, data)
        rt = h5file["metadata/acquisition/real_time"]
        assert rt.attrs["value"] == pytest.approx(3789.47)


# ---------------------------------------------------------------------------
# write() — fit
# ---------------------------------------------------------------------------


class TestWriteFit:
    def test_fit_group_created(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        assert "fit" in h5file

    def test_fit_attrs(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        fit = h5file["fit"]
        assert fit.attrs["_type"] == "multi_exponential"
        assert fit.attrs["_version"] == 1
        assert fit.attrs["chi_squared"] == pytest.approx(1.02)
        assert fit.attrs["degrees_of_freedom"] == 125

    def test_fit_curve_dataset(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        assert "fit/curve" in h5file
        assert h5file["fit/curve"].dtype == np.float32
        assert h5file["fit/curve"].shape == (128,)

    def test_fit_residuals_dataset(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        assert "fit/residuals" in h5file
        assert h5file["fit/residuals"].shape == (128,)

    def test_fit_components(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        assert "fit/components/component_0" in h5file
        assert "fit/components/component_1" in h5file

    def test_component_0_attrs(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        c0 = h5file["fit/components/component_0"]
        assert c0.attrs["label"] == "free positron"
        assert c0.attrs["intensity"] == pytest.approx(0.72)
        assert c0.attrs["intensity_error"] == pytest.approx(0.02)

    def test_component_0_lifetime(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        lt = h5file["fit/components/component_0/lifetime"]
        assert lt.attrs["value"] == pytest.approx(0.382)
        assert lt.attrs["units"] == "ns"
        assert lt.attrs["unitSI"] == pytest.approx(1e-9)

    def test_component_0_lifetime_error(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        lte = h5file["fit/components/component_0/lifetime_error"]
        assert lte.attrs["value"] == pytest.approx(0.005)

    def test_component_0_curve(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        assert "fit/components/component_0/curve" in h5file
        assert h5file["fit/components/component_0/curve"].dtype == np.float32

    def test_component_1_no_intensity_error(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        c1 = h5file["fit/components/component_1"]
        assert "intensity_error" not in c1.attrs

    def test_fit_parameters(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        params = h5file["fit/parameters"]
        names = [
            v.decode() if isinstance(v, bytes) else str(v)
            for v in params.attrs["names"]
        ]
        assert names == ["tau_1", "I_1", "tau_2", "I_2", "bg"]
        np.testing.assert_array_almost_equal(
            params.attrs["values"], [0.382, 0.72, 1.85, 0.28, 12.5]
        )
        np.testing.assert_array_almost_equal(
            params.attrs["errors"], [0.005, 0.02, 0.03, 0.02, 0.8]
        )

    def test_fit_description(self, schema, h5file):
        data = _1d_with_fit()
        schema.write(h5file, data)
        assert h5file["fit"].attrs["description"] == "PALS multi-exponential fit"


# ---------------------------------------------------------------------------
# write() — custom default attr
# ---------------------------------------------------------------------------


class TestCustomDefault:
    def test_custom_default_attr(self, schema, h5file):
        data = _1d_with_fit()
        data["default"] = "fit/curve"
        schema.write(h5file, data)
        assert h5file.attrs["default"] == "fit/curve"


# ---------------------------------------------------------------------------
# Entry point registration
# ---------------------------------------------------------------------------


class TestEntryPointRegistration:
    def test_factory_returns_spectrum_schema(self):
        from fd5.imaging.spectrum import SpectrumSchema

        instance = SpectrumSchema()
        assert instance.product_type == "spectrum"

    def test_register_schema_works(self):
        from fd5.imaging.spectrum import SpectrumSchema

        schema = SpectrumSchema()
        register_schema("spectrum", schema)

        from fd5.registry import get_schema

        retrieved = get_schema("spectrum")
        assert retrieved.product_type == "spectrum"


# ---------------------------------------------------------------------------
# Integration test — round-trip write/validate
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_create_validate_roundtrip_1d(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        register_schema("spectrum", schema)
        data = _minimal_1d_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-spectrum"
            f.attrs["description"] = "Integration test spectrum file"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_create_validate_roundtrip_2d(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        register_schema("spectrum", schema)
        data = _minimal_2d_data()
        with h5py.File(h5path, "w") as f:
            for k, v in schema.required_root_attrs().items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-coincidence"
            f.attrs["description"] = "Integration test 2D coincidence matrix"
            embed_schema(f, schema.json_schema())
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_create_validate_roundtrip_with_fit(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        register_schema("spectrum", schema)
        data = _1d_with_fit()
        with h5py.File(h5path, "w") as f:
            for k, v in schema.required_root_attrs().items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-pals"
            f.attrs["description"] = "Integration test PALS with fit"
            embed_schema(f, schema.json_schema())
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_generate_schema_for_spectrum(self, schema):
        register_schema("spectrum", schema)
        from fd5.schema import generate_schema

        result = generate_schema("spectrum")
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert result["properties"]["product"]["const"] == "spectrum"

    def test_full_roundtrip_with_metadata_and_errors(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        register_schema("spectrum", schema)
        data = _1d_with_metadata()
        data["counts_errors"] = np.sqrt(data["counts"])
        with h5py.File(h5path, "w") as f:
            for k, v in schema.required_root_attrs().items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-full"
            f.attrs["description"] = "Full integration test"
            embed_schema(f, schema.json_schema())
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

        with h5py.File(h5path, "r") as f:
            assert f.attrs["product"] == "spectrum"
            assert f.attrs["n_dimensions"] == 1
            assert "counts" in f
            assert "counts_errors" in f
            assert "metadata/method" in f
            assert "metadata/acquisition" in f
            assert "axes/ax0/bin_edges" in f
            assert "axes/ax0/bin_centers" in f
