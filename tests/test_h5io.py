"""Tests for fd5.h5io — dict_to_h5 and h5_to_dict round-trip helpers."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from fd5.h5io import dict_to_h5, h5_to_dict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def h5group(tmp_path):
    """Yield a writable HDF5 group, auto-closed after test."""
    path = tmp_path / "test.h5"
    with h5py.File(path, "w") as f:
        yield f


# ---------------------------------------------------------------------------
# dict_to_h5 — scalar types
# ---------------------------------------------------------------------------


class TestDictToH5Scalars:
    def test_str(self, h5group):
        dict_to_h5(h5group, {"name": "Alice"})
        assert h5group.attrs["name"] == "Alice"

    def test_int(self, h5group):
        dict_to_h5(h5group, {"count": 42})
        assert h5group.attrs["count"] == 42

    def test_float(self, h5group):
        dict_to_h5(h5group, {"ratio": 3.14})
        assert h5group.attrs["ratio"] == pytest.approx(3.14)

    def test_bool_true(self, h5group):
        dict_to_h5(h5group, {"flag": True})
        assert h5group.attrs["flag"] is np.True_

    def test_bool_false(self, h5group):
        dict_to_h5(h5group, {"flag": False})
        assert h5group.attrs["flag"] is np.False_

    def test_none_skipped(self, h5group):
        dict_to_h5(h5group, {"missing": None})
        assert "missing" not in h5group.attrs

    def test_none_mixed_with_values(self, h5group):
        dict_to_h5(h5group, {"a": 1, "b": None, "c": "hello"})
        assert "a" in h5group.attrs
        assert "b" not in h5group.attrs
        assert "c" in h5group.attrs


# ---------------------------------------------------------------------------
# dict_to_h5 — nested dicts (sub-groups)
# ---------------------------------------------------------------------------


class TestDictToH5Nested:
    def test_nested_dict_creates_subgroup(self, h5group):
        dict_to_h5(h5group, {"sub": {"x": 1}})
        assert "sub" in h5group
        assert h5group["sub"].attrs["x"] == 1

    def test_deeply_nested(self, h5group):
        dict_to_h5(h5group, {"a": {"b": {"c": 99}}})
        assert h5group["a"]["b"].attrs["c"] == 99

    def test_empty_dict_creates_empty_group(self, h5group):
        dict_to_h5(h5group, {"empty": {}})
        assert "empty" in h5group
        assert len(h5group["empty"].attrs) == 0


# ---------------------------------------------------------------------------
# dict_to_h5 — sorted keys
# ---------------------------------------------------------------------------


class TestDictToH5SortedKeys:
    def test_keys_written_in_sorted_order(self, h5group):
        dict_to_h5(h5group, {"z": 1, "a": 2, "m": 3})
        assert list(h5group.attrs.keys()) == ["a", "m", "z"]


# ---------------------------------------------------------------------------
# dict_to_h5 — list types
# ---------------------------------------------------------------------------


class TestDictToH5Lists:
    def test_list_int(self, h5group):
        dict_to_h5(h5group, {"vals": [1, 2, 3]})
        result = h5group.attrs["vals"]
        np.testing.assert_array_equal(result, [1, 2, 3])

    def test_list_float(self, h5group):
        dict_to_h5(h5group, {"vals": [1.1, 2.2, 3.3]})
        result = h5group.attrs["vals"]
        np.testing.assert_array_almost_equal(result, [1.1, 2.2, 3.3])

    def test_list_str(self, h5group):
        dict_to_h5(h5group, {"tags": ["a", "b", "c"]})
        result = list(h5group.attrs["tags"])
        assert result == ["a", "b", "c"]

    def test_list_bool(self, h5group):
        dict_to_h5(h5group, {"flags": [True, False, True]})
        result = h5group.attrs["flags"]
        np.testing.assert_array_equal(result, [True, False, True])
        assert result.dtype == np.bool_

    def test_empty_list(self, h5group):
        dict_to_h5(h5group, {"empty": []})
        result = h5group.attrs["empty"]
        assert len(result) == 0

    def test_list_mixed_numeric(self, h5group):
        dict_to_h5(h5group, {"mixed": [1, 2.5, 3]})
        result = h5group.attrs["mixed"]
        np.testing.assert_array_almost_equal(result, [1, 2.5, 3])


# ---------------------------------------------------------------------------
# h5_to_dict — reading attrs
# ---------------------------------------------------------------------------


class TestH5ToDict:
    def test_read_str(self, h5group):
        h5group.attrs["name"] = "Alice"
        result = h5_to_dict(h5group)
        assert result == {"name": "Alice"}
        assert isinstance(result["name"], str)

    def test_read_int(self, h5group):
        h5group.attrs["count"] = np.int64(42)
        result = h5_to_dict(h5group)
        assert result == {"count": 42}
        assert isinstance(result["count"], int)

    def test_read_float(self, h5group):
        h5group.attrs["ratio"] = np.float64(3.14)
        result = h5_to_dict(h5group)
        assert result["ratio"] == pytest.approx(3.14)
        assert isinstance(result["ratio"], float)

    def test_read_bool(self, h5group):
        h5group.attrs["flag"] = np.bool_(True)
        result = h5_to_dict(h5group)
        assert result == {"flag": True}
        assert isinstance(result["flag"], bool)

    def test_read_subgroup(self, h5group):
        sub = h5group.create_group("sub")
        sub.attrs["x"] = np.int64(1)
        result = h5_to_dict(h5group)
        assert result == {"sub": {"x": 1}}

    def test_empty_group(self, h5group):
        result = h5_to_dict(h5group)
        assert result == {}

    def test_read_numeric_array(self, h5group):
        h5group.attrs["vals"] = np.array([1, 2, 3], dtype=np.int64)
        result = h5_to_dict(h5group)
        assert result["vals"] == [1, 2, 3]
        assert isinstance(result["vals"], list)

    def test_read_float_array(self, h5group):
        h5group.attrs["vals"] = np.array([1.1, 2.2], dtype=np.float64)
        result = h5_to_dict(h5group)
        assert result["vals"] == pytest.approx([1.1, 2.2])

    def test_read_string_array(self, h5group):
        dt = h5py.special_dtype(vlen=str)
        h5group.attrs.create("tags", data=["a", "b"], dtype=dt)
        result = h5_to_dict(h5group)
        assert result["tags"] == ["a", "b"]

    def test_read_bool_array(self, h5group):
        h5group.attrs["flags"] = np.array([True, False], dtype=np.bool_)
        result = h5_to_dict(h5group)
        assert result["flags"] == [True, False]
        assert all(isinstance(v, bool) for v in result["flags"])

    def test_datasets_skipped(self, h5group):
        h5group.attrs["meta"] = "value"
        h5group.create_dataset("volume", data=np.zeros((10, 10)))
        result = h5_to_dict(h5group)
        assert "volume" not in result
        assert result == {"meta": "value"}

    def test_datasets_in_subgroup_skipped(self, h5group):
        sub = h5group.create_group("sub")
        sub.attrs["x"] = np.int64(1)
        sub.create_dataset("data", data=np.zeros(5))
        result = h5_to_dict(h5group)
        assert "data" not in result["sub"]
        assert result == {"sub": {"x": 1}}

    def test_absent_attr_means_missing_key(self, h5group):
        h5group.attrs["present"] = "yes"
        result = h5_to_dict(h5group)
        assert "present" in result
        assert "absent" not in result


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_complex_nested(self, h5group):
        original = {
            "acquisition": {
                "date": "2026-01-15",
                "duration_s": 300.5,
                "num_frames": 100,
                "is_gated": True,
            },
            "instrument": {
                "model": "Scanner-X",
                "calibration": {
                    "date": "2025-12-01",
                    "version": 3,
                },
            },
            "processing": {
                "algorithm": "osem",
                "iterations": 4,
                "subsets": 21,
                "use_tof": False,
                "voxel_size": [2.0, 2.0, 2.0],
            },
            "tags": ["clinical", "brain"],
        }
        dict_to_h5(h5group, original)
        result = h5_to_dict(h5group)
        assert result == original

    def test_round_trip_empty_dict(self, h5group):
        dict_to_h5(h5group, {})
        assert h5_to_dict(h5group) == {}

    def test_round_trip_scalars(self, h5group):
        original = {"a": 1, "b": 2.0, "c": "three", "d": True}
        dict_to_h5(h5group, original)
        assert h5_to_dict(h5group) == original

    def test_round_trip_with_none_values(self, h5group):
        original = {"present": "yes", "absent": None}
        dict_to_h5(h5group, original)
        result = h5_to_dict(h5group)
        assert result == {"present": "yes"}

    def test_round_trip_list_types(self, h5group):
        original = {
            "bools": [True, False, True],
            "floats": [1.1, 2.2],
            "ints": [10, 20, 30],
            "strings": ["x", "y"],
        }
        dict_to_h5(h5group, original)
        result = h5_to_dict(h5group)
        assert result == original


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_unsupported_type_raises_typeerror(self, h5group):
        with pytest.raises(TypeError, match="Unsupported type"):
            dict_to_h5(h5group, {"bad": object()})

    def test_unsupported_type_in_nested(self, h5group):
        with pytest.raises(TypeError, match="Unsupported type"):
            dict_to_h5(h5group, {"sub": {"bad": set()}})

    def test_unsupported_list_element_type(self, h5group):
        with pytest.raises(TypeError, match="Unsupported type"):
            dict_to_h5(h5group, {"bad": [object()]})
