"""Tests for fd5.units — physical quantity convention helpers."""

import numpy as np
import h5py
import pytest

from fd5.units import read_quantity, set_dataset_units, write_quantity


@pytest.fixture()
def h5_group(tmp_path):
    """Yield a writable HDF5 group backed by a temp file."""
    path = tmp_path / "test.h5"
    with h5py.File(path, "w") as f:
        yield f


class TestWriteQuantity:
    """Tests for write_quantity."""

    def test_creates_subgroup_with_attrs(self, h5_group):
        write_quantity(h5_group, "z_min", -450.2, "mm", 0.001)

        grp = h5_group["z_min"]
        assert grp.attrs["value"] == pytest.approx(-450.2)
        assert grp.attrs["units"] == "mm"
        assert grp.attrs["unitSI"] == pytest.approx(0.001)

    def test_returns_created_group(self, h5_group):
        result = write_quantity(h5_group, "duration", 367.0, "s", 1.0)
        assert isinstance(result, h5py.Group)
        assert result.name.endswith("/duration")

    def test_integer_value(self, h5_group):
        write_quantity(h5_group, "kvp", 120, "kV", 1000.0)

        grp = h5_group["kvp"]
        assert grp.attrs["value"] == 120
        assert grp.attrs["units"] == "kV"
        assert grp.attrs["unitSI"] == pytest.approx(1000.0)

    def test_list_value(self, h5_group):
        write_quantity(h5_group, "grid_spacing", [4.0, 4.0, 4.0], "mm", 0.001)

        grp = h5_group["grid_spacing"]
        np.testing.assert_array_almost_equal(grp.attrs["value"], [4.0, 4.0, 4.0])
        assert grp.attrs["units"] == "mm"

    def test_numpy_array_value(self, h5_group):
        arr = np.array([120.0, 120.0, 120.0, 120.0])
        write_quantity(h5_group, "frame_durations", arr, "s", 1.0)

        grp = h5_group["frame_durations"]
        np.testing.assert_array_almost_equal(grp.attrs["value"], arr)

    def test_overwrites_existing_group_raises(self, h5_group):
        write_quantity(h5_group, "z_min", -450.2, "mm", 0.001)
        with pytest.raises(ValueError, match="already exists"):
            write_quantity(h5_group, "z_min", -450.2, "mm", 0.001)


class TestReadQuantity:
    """Tests for read_quantity."""

    def test_round_trip_scalar(self, h5_group):
        write_quantity(h5_group, "duration", 367.0, "s", 1.0)

        value, units, unit_si = read_quantity(h5_group, "duration")
        assert value == pytest.approx(367.0)
        assert units == "s"
        assert unit_si == pytest.approx(1.0)

    def test_round_trip_integer(self, h5_group):
        write_quantity(h5_group, "kvp", 120, "kV", 1000.0)

        value, units, unit_si = read_quantity(h5_group, "kvp")
        assert value == 120
        assert units == "kV"
        assert unit_si == pytest.approx(1000.0)

    def test_round_trip_list(self, h5_group):
        write_quantity(h5_group, "grid_spacing", [4.0, 4.0, 4.0], "mm", 0.001)

        value, units, unit_si = read_quantity(h5_group, "grid_spacing")
        np.testing.assert_array_almost_equal(value, [4.0, 4.0, 4.0])
        assert units == "mm"
        assert unit_si == pytest.approx(0.001)

    def test_missing_quantity_raises(self, h5_group):
        with pytest.raises(KeyError):
            read_quantity(h5_group, "nonexistent")

    def test_missing_attrs_raises(self, h5_group):
        h5_group.create_group("bad_group")
        with pytest.raises(KeyError):
            read_quantity(h5_group, "bad_group")


class TestSetDatasetUnits:
    """Tests for set_dataset_units."""

    def test_sets_units_and_unit_si(self, h5_group):
        ds = h5_group.create_dataset("volume", data=np.zeros((2, 3, 4)))
        set_dataset_units(ds, "Bq/mL", 1000.0)

        assert ds.attrs["units"] == "Bq/mL"
        assert ds.attrs["unitSI"] == pytest.approx(1000.0)

    def test_preserves_existing_attrs(self, h5_group):
        ds = h5_group.create_dataset("signal", data=np.zeros(100))
        ds.attrs["description"] = "Raw ECG signal"

        set_dataset_units(ds, "mV", 0.001)

        assert ds.attrs["description"] == "Raw ECG signal"
        assert ds.attrs["units"] == "mV"
        assert ds.attrs["unitSI"] == pytest.approx(0.001)

    def test_overwrites_existing_units(self, h5_group):
        ds = h5_group.create_dataset("time", data=np.zeros(50))
        set_dataset_units(ds, "ms", 0.001)
        set_dataset_units(ds, "s", 1.0)

        assert ds.attrs["units"] == "s"
        assert ds.attrs["unitSI"] == pytest.approx(1.0)


class TestIdempotency:
    """Verify write-then-read returns identical values."""

    @pytest.mark.parametrize(
        "name,value,units,unit_si",
        [
            ("activity", 350.0, "MBq", 1e6),
            ("half_life", 6586.2, "s", 1.0),
            ("ctdi_vol", 12.5, "mGy", 0.001),
            ("angular_range", [-30, 30], "mrad", 0.001),
        ],
    )
    def test_round_trip_parametrized(self, h5_group, name, value, units, unit_si):
        write_quantity(h5_group, name, value, units, unit_si)
        got_value, got_units, got_unit_si = read_quantity(h5_group, name)

        if isinstance(value, list):
            np.testing.assert_array_almost_equal(got_value, value)
        else:
            assert got_value == pytest.approx(value)
        assert got_units == units
        assert got_unit_si == pytest.approx(unit_si)
