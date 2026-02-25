"""Tests for fd5.imaging.calibration — CalibrationSchema product schema."""

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
    from fd5.imaging.calibration import CalibrationSchema

    return CalibrationSchema()


@pytest.fixture()
def h5file(tmp_path):
    path = tmp_path / "calibration.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path):
    return tmp_path / "calibration.h5"


def _base_data(**overrides: object) -> dict:
    """Minimal required fields for any calibration write."""
    d: dict = {
        "calibration_type": "normalization",
        "scanner_model": "GE Discovery MI",
        "scanner_serial": "SN-12345",
        "valid_from": "2025-01-15T08:00:00Z",
        "valid_until": "2025-07-15T08:00:00Z",
    }
    d.update(overrides)
    return d


def _normalization_data() -> dict:
    rng = np.random.default_rng(42)
    return _base_data(
        calibration_type="normalization",
        default="data/norm_factors",
        norm_factors=rng.random((36, 672), dtype=np.float32),
        efficiency_map=rng.random((36, 672), dtype=np.float32),
        metadata={
            "calibration": {
                "_type": "normalization",
                "_version": 1,
                "description": "Component-based normalization",
                "method": "component_based",
                "n_crystals_axial": 36,
                "n_crystals_transaxial": 672,
                "acquisition_duration": {
                    "value": 14400.0,
                    "units": "s",
                    "unitSI": 1.0,
                },
            },
            "conditions": {
                "description": "Environmental conditions during calibration",
                "temperature": {"value": 22.0, "units": "degC", "unitSI": 1.0},
                "humidity": {"value": 45.0, "units": "%", "unitSI": 0.01},
            },
        },
    )


def _energy_calibration_data() -> dict:
    n_channels = 1024
    rng = np.random.default_rng(7)
    return _base_data(
        calibration_type="energy_calibration",
        default="data/channel_to_energy",
        channel_to_energy=np.linspace(0.0, 1500.0, n_channels),
        reference_spectrum=rng.random(n_channels).astype(np.float64),
        metadata={
            "calibration": {
                "_type": "energy_calibration",
                "_version": 1,
                "description": "Channel-to-energy mapping",
                "n_channels": n_channels,
                "fit_model": "linear",
                "coefficients": [0.0, 1.47],
                "coefficients_labels": ["offset", "gain"],
                "reference_sources": ["22Na", "137Cs"],
            },
        },
    )


def _gain_map_data() -> dict:
    rng = np.random.default_rng(3)
    return _base_data(
        calibration_type="gain_map",
        default="data/gain_map",
        gain_map=rng.random((36, 672), dtype=np.float32),
    )


def _dead_time_data() -> dict:
    n_points = 50
    count_rates = np.linspace(1e3, 1e6, n_points)
    corrections = 1.0 + 1e-7 * count_rates
    curve = np.column_stack([count_rates, corrections])
    return _base_data(
        calibration_type="dead_time",
        default="data/dead_time_curve",
        dead_time_curve=curve,
    )


def _timing_calibration_data() -> dict:
    rng = np.random.default_rng(9)
    n_crystals = 672
    n_points = 20
    return _base_data(
        calibration_type="timing_calibration",
        default="data/timing_offsets",
        timing_offsets=rng.standard_normal(n_crystals).astype(np.float32),
        resolution_curve=np.column_stack(
            [
                np.linspace(100.0, 600.0, n_points),
                rng.uniform(0.3, 0.6, n_points),
            ]
        ),
    )


def _crystal_map_data() -> dict:
    n_crystals = 100
    rng = np.random.default_rng(11)
    return _base_data(
        calibration_type="crystal_map",
        default="data/crystal_positions",
        crystal_positions=rng.random((n_crystals, 3)),
        crystal_ids=np.arange(n_crystals, dtype=np.int64),
    )


def _sensitivity_data() -> dict:
    return _base_data(
        calibration_type="sensitivity",
        default="data/sensitivity_profile",
        sensitivity_profile=np.linspace(0.8, 1.2, 36),
    )


def _cross_calibration_data() -> dict:
    return _base_data(
        calibration_type="cross_calibration",
        metadata={
            "calibration": {
                "_type": "cross_calibration",
                "_version": 1,
                "description": "Scanner-to-dose-calibrator cross-calibration",
                "reference_instrument": "dose_calibrator",
                "reference_model": "Capintec CRC-55tR",
                "calibration_factor": 1.023,
                "calibration_factor_error": 0.008,
                "phantom": "uniform_cylinder",
                "activity": {"value": 45.0, "units": "MBq", "unitSI": 1e6},
            },
        },
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_product_schema_protocol(self, schema):
        assert isinstance(schema, ProductSchema)

    def test_product_type_is_calibration(self, schema):
        assert schema.product_type == "calibration"

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

    def test_product_const_is_calibration(self, schema):
        result = schema.json_schema()
        assert result["properties"]["product"]["const"] == "calibration"

    def test_calibration_type_enum(self, schema):
        result = schema.json_schema()
        enum_values = result["properties"]["calibration_type"]["enum"]
        assert "normalization" in enum_values
        assert "energy_calibration" in enum_values
        assert "gain_map" in enum_values

    def test_required_fields(self, schema):
        result = schema.json_schema()
        required = result["required"]
        assert "product" in required
        assert "calibration_type" in required
        assert "scanner_model" in required
        assert "scanner_serial" in required
        assert "valid_from" in required
        assert "valid_until" in required

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

    def test_contains_product_calibration(self, schema):
        result = schema.required_root_attrs()
        assert result["product"] == "calibration"

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

    def test_contains_calibration_identifiers(self, schema):
        result = schema.id_inputs()
        assert "calibration_type" in result
        assert "scanner_model" in result
        assert "scanner_serial" in result
        assert "valid_from" in result


# ---------------------------------------------------------------------------
# write() — root attrs
# ---------------------------------------------------------------------------


class TestWriteRootAttrs:
    def test_writes_calibration_type(self, schema, h5file):
        data = _base_data()
        schema.write(h5file, data)
        assert h5file.attrs["calibration_type"] == "normalization"

    def test_writes_scanner_model(self, schema, h5file):
        data = _base_data()
        schema.write(h5file, data)
        assert h5file.attrs["scanner_model"] == "GE Discovery MI"

    def test_writes_scanner_serial(self, schema, h5file):
        data = _base_data()
        schema.write(h5file, data)
        assert h5file.attrs["scanner_serial"] == "SN-12345"

    def test_writes_valid_from(self, schema, h5file):
        data = _base_data()
        schema.write(h5file, data)
        assert h5file.attrs["valid_from"] == "2025-01-15T08:00:00Z"

    def test_writes_valid_until(self, schema, h5file):
        data = _base_data()
        schema.write(h5file, data)
        assert h5file.attrs["valid_until"] == "2025-07-15T08:00:00Z"

    def test_writes_default_attr(self, schema, h5file):
        data = _base_data(default="data/norm_factors")
        schema.write(h5file, data)
        assert h5file.attrs["default"] == "data/norm_factors"

    def test_no_default_when_omitted(self, schema, h5file):
        data = _base_data()
        schema.write(h5file, data)
        assert "default" not in h5file.attrs


# ---------------------------------------------------------------------------
# write() — normalization
# ---------------------------------------------------------------------------


class TestWriteNormalization:
    def test_norm_factors_dataset(self, schema, h5file):
        data = _normalization_data()
        schema.write(h5file, data)
        assert "data/norm_factors" in h5file
        assert h5file["data/norm_factors"].dtype == np.float32
        assert h5file["data/norm_factors"].shape == (36, 672)

    def test_norm_factors_compressed(self, schema, h5file):
        data = _normalization_data()
        schema.write(h5file, data)
        ds = h5file["data/norm_factors"]
        assert ds.compression == "gzip"
        assert ds.compression_opts == 4

    def test_efficiency_map_dataset(self, schema, h5file):
        data = _normalization_data()
        schema.write(h5file, data)
        assert "data/efficiency_map" in h5file
        assert h5file["data/efficiency_map"].dtype == np.float32
        assert h5file["data/efficiency_map"].shape == (36, 672)

    def test_metadata_calibration_group(self, schema, h5file):
        data = _normalization_data()
        schema.write(h5file, data)
        grp = h5file["metadata/calibration"]
        assert grp.attrs["_type"] == "normalization"
        assert grp.attrs["_version"] == 1
        assert grp.attrs["method"] == "component_based"

    def test_metadata_conditions_group(self, schema, h5file):
        data = _normalization_data()
        schema.write(h5file, data)
        cond = h5file["metadata/conditions"]
        assert "description" in cond.attrs
        temp = h5file["metadata/conditions/temperature"]
        assert float(temp.attrs["value"]) == pytest.approx(22.0)
        assert temp.attrs["units"] == "degC"

    def test_metadata_acquisition_duration(self, schema, h5file):
        data = _normalization_data()
        schema.write(h5file, data)
        dur = h5file["metadata/calibration/acquisition_duration"]
        assert float(dur.attrs["value"]) == pytest.approx(14400.0)
        assert dur.attrs["units"] == "s"


# ---------------------------------------------------------------------------
# write() — energy calibration
# ---------------------------------------------------------------------------


class TestWriteEnergyCalibration:
    def test_channel_to_energy_dataset(self, schema, h5file):
        data = _energy_calibration_data()
        schema.write(h5file, data)
        assert "data/channel_to_energy" in h5file
        ds = h5file["data/channel_to_energy"]
        assert ds.dtype == np.float64
        assert ds.shape == (1024,)
        assert ds.attrs["units"] == "keV"

    def test_reference_spectrum_dataset(self, schema, h5file):
        data = _energy_calibration_data()
        schema.write(h5file, data)
        assert "data/reference_spectrum" in h5file
        ds = h5file["data/reference_spectrum"]
        assert ds.dtype == np.float64
        assert ds.shape == (1024,)

    def test_metadata_coefficients(self, schema, h5file):
        data = _energy_calibration_data()
        schema.write(h5file, data)
        grp = h5file["metadata/calibration"]
        assert grp.attrs["fit_model"] == "linear"
        np.testing.assert_array_almost_equal(grp.attrs["coefficients"], [0.0, 1.47])

    def test_metadata_string_list_attrs(self, schema, h5file):
        data = _energy_calibration_data()
        schema.write(h5file, data)
        grp = h5file["metadata/calibration"]
        labels = [
            v.decode() if isinstance(v, bytes) else str(v)
            for v in grp.attrs["coefficients_labels"]
        ]
        assert labels == ["offset", "gain"]
        sources = [
            v.decode() if isinstance(v, bytes) else str(v)
            for v in grp.attrs["reference_sources"]
        ]
        assert sources == ["22Na", "137Cs"]


# ---------------------------------------------------------------------------
# write() — gain map
# ---------------------------------------------------------------------------


class TestWriteGainMap:
    def test_gain_map_dataset(self, schema, h5file):
        data = _gain_map_data()
        schema.write(h5file, data)
        assert "data/gain_map" in h5file
        ds = h5file["data/gain_map"]
        assert ds.dtype == np.float32
        assert ds.shape == (36, 672)
        assert ds.attrs["description"] == "Per-crystal gain correction factors"

    def test_gain_map_compressed(self, schema, h5file):
        data = _gain_map_data()
        schema.write(h5file, data)
        ds = h5file["data/gain_map"]
        assert ds.compression == "gzip"


# ---------------------------------------------------------------------------
# write() — dead time
# ---------------------------------------------------------------------------


class TestWriteDeadTime:
    def test_dead_time_curve_dataset(self, schema, h5file):
        data = _dead_time_data()
        schema.write(h5file, data)
        assert "data/dead_time_curve" in h5file
        ds = h5file["data/dead_time_curve"]
        assert ds.dtype == np.float64
        assert ds.shape == (50, 2)
        assert ds.attrs["count_rate__units"] == "cps"


# ---------------------------------------------------------------------------
# write() — timing calibration
# ---------------------------------------------------------------------------


class TestWriteTimingCalibration:
    def test_timing_offsets_dataset(self, schema, h5file):
        data = _timing_calibration_data()
        schema.write(h5file, data)
        assert "data/timing_offsets" in h5file
        ds = h5file["data/timing_offsets"]
        assert ds.dtype == np.float32
        assert ds.shape == (672,)
        assert ds.attrs["units"] == "ns"

    def test_timing_offsets_compressed(self, schema, h5file):
        data = _timing_calibration_data()
        schema.write(h5file, data)
        ds = h5file["data/timing_offsets"]
        assert ds.compression == "gzip"

    def test_resolution_curve_dataset(self, schema, h5file):
        data = _timing_calibration_data()
        schema.write(h5file, data)
        assert "data/resolution_curve" in h5file
        ds = h5file["data/resolution_curve"]
        assert ds.dtype == np.float64
        assert ds.shape == (20, 2)
        assert ds.attrs["energy__units"] == "keV"
        assert ds.attrs["fwhm__units"] == "ns"


# ---------------------------------------------------------------------------
# write() — crystal map
# ---------------------------------------------------------------------------


class TestWriteCrystalMap:
    def test_crystal_positions_dataset(self, schema, h5file):
        data = _crystal_map_data()
        schema.write(h5file, data)
        assert "data/crystal_positions" in h5file
        ds = h5file["data/crystal_positions"]
        assert ds.dtype == np.float64
        assert ds.shape == (100, 3)

    def test_crystal_ids_dataset(self, schema, h5file):
        data = _crystal_map_data()
        schema.write(h5file, data)
        assert "data/crystal_ids" in h5file
        ds = h5file["data/crystal_ids"]
        assert ds.dtype == np.int64
        assert ds.shape == (100,)


# ---------------------------------------------------------------------------
# write() — sensitivity
# ---------------------------------------------------------------------------


class TestWriteSensitivity:
    def test_sensitivity_profile_dataset(self, schema, h5file):
        data = _sensitivity_data()
        schema.write(h5file, data)
        assert "data/sensitivity_profile" in h5file
        ds = h5file["data/sensitivity_profile"]
        assert ds.dtype == np.float64
        assert ds.shape == (36,)


# ---------------------------------------------------------------------------
# write() — cross calibration
# ---------------------------------------------------------------------------


class TestWriteCrossCalibration:
    def test_metadata_only(self, schema, h5file):
        data = _cross_calibration_data()
        schema.write(h5file, data)
        grp = h5file["metadata/calibration"]
        assert grp.attrs["_type"] == "cross_calibration"
        assert float(grp.attrs["calibration_factor"]) == pytest.approx(1.023)
        assert grp.attrs["phantom"] == "uniform_cylinder"

    def test_cross_cal_activity_subgroup(self, schema, h5file):
        data = _cross_calibration_data()
        schema.write(h5file, data)
        act = h5file["metadata/calibration/activity"]
        assert float(act.attrs["value"]) == pytest.approx(45.0)
        assert act.attrs["units"] == "MBq"

    def test_no_data_group_for_cross_calibration(self, schema, h5file):
        data = _cross_calibration_data()
        schema.write(h5file, data)
        assert "data" not in h5file


# ---------------------------------------------------------------------------
# Round-trip: write → read-back
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_normalization_roundtrip(self, schema, h5path):
        data = _normalization_data()
        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            np.testing.assert_array_almost_equal(
                f["data/norm_factors"][:], data["norm_factors"]
            )
            np.testing.assert_array_almost_equal(
                f["data/efficiency_map"][:], data["efficiency_map"]
            )
            assert f.attrs["calibration_type"] == "normalization"
            assert f.attrs["scanner_model"] == "GE Discovery MI"

    def test_energy_calibration_roundtrip(self, schema, h5path):
        data = _energy_calibration_data()
        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            np.testing.assert_array_almost_equal(
                f["data/channel_to_energy"][:], data["channel_to_energy"]
            )
            np.testing.assert_array_almost_equal(
                f["data/reference_spectrum"][:], data["reference_spectrum"]
            )

    def test_timing_calibration_roundtrip(self, schema, h5path):
        data = _timing_calibration_data()
        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            np.testing.assert_array_almost_equal(
                f["data/timing_offsets"][:], data["timing_offsets"]
            )
            np.testing.assert_array_almost_equal(
                f["data/resolution_curve"][:], data["resolution_curve"]
            )

    def test_crystal_map_roundtrip(self, schema, h5path):
        data = _crystal_map_data()
        with h5py.File(h5path, "w") as f:
            schema.write(f, data)

        with h5py.File(h5path, "r") as f:
            np.testing.assert_array_almost_equal(
                f["data/crystal_positions"][:], data["crystal_positions"]
            )
            np.testing.assert_array_equal(f["data/crystal_ids"][:], data["crystal_ids"])


# ---------------------------------------------------------------------------
# Registration via register_schema()
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_factory_returns_calibration_schema(self):
        from fd5.imaging.calibration import CalibrationSchema

        instance = CalibrationSchema()
        assert instance.product_type == "calibration"

    def test_register_and_generate_schema(self, schema):
        register_schema("calibration", schema)
        from fd5.schema import generate_schema

        result = generate_schema("calibration")
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert result["properties"]["product"]["const"] == "calibration"


# ---------------------------------------------------------------------------
# Integration: write + embed_schema + validate
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_create_validate_roundtrip(self, schema, h5path):
        from fd5.schema import embed_schema, validate

        data = _normalization_data()
        with h5py.File(h5path, "w") as f:
            root_attrs = schema.required_root_attrs()
            for k, v in root_attrs.items():
                f.attrs[k] = v
            f.attrs["name"] = "integration-test-calibration"
            f.attrs["description"] = "Integration test calibration file"
            schema_dict = schema.json_schema()
            embed_schema(f, schema_dict)
            schema.write(f, data)

        errors = validate(h5path)
        assert errors == [], [e.message for e in errors]

    def test_all_calibration_types_validate(self, schema, h5path):
        """Every calibration type produces a file that passes validation."""
        from fd5.schema import embed_schema, validate

        factories = [
            _normalization_data,
            _energy_calibration_data,
            _gain_map_data,
            _dead_time_data,
            _timing_calibration_data,
            _crystal_map_data,
            _sensitivity_data,
            _cross_calibration_data,
        ]

        for factory in factories:
            data = factory()
            with h5py.File(h5path, "w") as f:
                root_attrs = schema.required_root_attrs()
                for k, v in root_attrs.items():
                    f.attrs[k] = v
                f.attrs["name"] = f"test-{data['calibration_type']}"
                f.attrs["description"] = f"Test {data['calibration_type']}"
                embed_schema(f, schema.json_schema())
                schema.write(f, data)

            errors = validate(h5path)
            assert errors == [], (
                f"{data['calibration_type']}: {[e.message for e in errors]}"
            )
