"""Tests for fd5.units module."""

import h5py
import numpy as np
import pytest

from fd5.units import read_quantity, set_dataset_units, write_quantity


@pytest.fixture()
def h5_group(tmp_path):
    """Yield an open HDF5 group backed by a temp file."""
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

    def test_integer_value(self, h5_group):
        write_quantity(h5_group, "kvp", 120, "kV", 1000.0)

        grp = h5_group["kvp"]
        assert grp.attrs["value"] == 120
        assert grp.attrs["units"] == "kV"
        assert grp.attrs["unitSI"] == pytest.approx(1000.0)

    def test_list_value(self, h5_group):
        write_quantity(h5_group, "grid_spacing", [4.0, 4.0, 4.0], "mm", 0.001)

        grp = h5_group["grid_spacing"]
        np.testing.assert_array_equal(grp.attrs["value"], [4.0, 4.0, 4.0])
        assert grp.attrs["units"] == "mm"

    def test_numpy_array_value(self, h5_group):
        arr = np.array([1.0, 2.0, 3.0])
        write_quantity(h5_group, "offsets", arr, "mm", 0.001)

        grp = h5_group["offsets"]
        np.testing.assert_array_equal(grp.attrs["value"], arr)

    def test_overwrites_existing_quantity(self, h5_group):
        write_quantity(h5_group, "duration", 100.0, "s", 1.0)
        write_quantity(h5_group, "duration", 200.0, "s", 1.0)

        assert h5_group["duration"].attrs["value"] == pytest.approx(200.0)


class TestReadQuantity:
    """Tests for read_quantity."""

    def test_reads_back_scalar(self, h5_group):
        write_quantity(h5_group, "duration", 367.0, "s", 1.0)

        value, units, unit_si = read_quantity(h5_group, "duration")
        assert value == pytest.approx(367.0)
        assert units == "s"
        assert unit_si == pytest.approx(1.0)

    def test_reads_back_array(self, h5_group):
        write_quantity(h5_group, "frame_durations", [120.0, 120.0], "s", 1.0)

        value, units, unit_si = read_quantity(h5_group, "frame_durations")
        np.testing.assert_array_equal(value, [120.0, 120.0])
        assert units == "s"

    def test_missing_quantity_raises_keyerror(self, h5_group):
        with pytest.raises(KeyError):
            read_quantity(h5_group, "nonexistent")


class TestSetDatasetUnits:
    """Tests for set_dataset_units."""

    def test_sets_units_and_unitsi_attrs(self, h5_group):
        ds = h5_group.create_dataset("volume", data=np.zeros((2, 2, 2)))
        set_dataset_units(ds, "Bq/mL", 1000.0)

        assert ds.attrs["units"] == "Bq/mL"
        assert ds.attrs["unitSI"] == pytest.approx(1000.0)

    def test_overwrites_existing_units(self, h5_group):
        ds = h5_group.create_dataset("signal", data=np.zeros(10))
        set_dataset_units(ds, "mV", 0.001)
        set_dataset_units(ds, "V", 1.0)

        assert ds.attrs["units"] == "V"
        assert ds.attrs["unitSI"] == pytest.approx(1.0)


class TestRoundTrip:
    """Round-trip: write then read returns identical values."""

    def test_scalar_round_trip(self, h5_group):
        write_quantity(h5_group, "activity", 350.0, "MBq", 1e6)
        value, units, unit_si = read_quantity(h5_group, "activity")

        assert value == pytest.approx(350.0)
        assert units == "MBq"
        assert unit_si == pytest.approx(1e6)

    def test_array_round_trip(self, h5_group):
        original = [4.0, 4.0, 4.0]
        write_quantity(h5_group, "grid_spacing", original, "mm", 0.001)
        value, units, unit_si = read_quantity(h5_group, "grid_spacing")

        np.testing.assert_array_equal(value, original)
        assert units == "mm"
        assert unit_si == pytest.approx(0.001)

    def test_negative_value_round_trip(self, h5_group):
        write_quantity(h5_group, "z_min", -850.0, "mm", 0.001)
        value, units, unit_si = read_quantity(h5_group, "z_min")

        assert value == pytest.approx(-850.0)
        assert units == "mm"
        assert unit_si == pytest.approx(0.001)
