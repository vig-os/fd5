"""fd5.h5io — lossless round-trip between Python dicts and HDF5 groups/attrs.

Type mapping follows white-paper.md § Implementation Notes.
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np


def dict_to_h5(group: h5py.Group, d: dict[str, Any]) -> None:
    """Write a Python dict as HDF5 attributes and sub-groups.

    Keys are written in sorted order for deterministic layout.
    ``None`` values are skipped (absence encodes None).
    """
    for key in sorted(d.keys()):
        value = d[key]
        if value is None:
            continue
        _write_value(group, key, value)


def h5_to_dict(group: h5py.Group) -> dict[str, Any]:
    """Read HDF5 attrs and sub-groups back to a Python dict.

    Datasets are never read — only attributes and groups.
    """
    result: dict[str, Any] = {}
    for key in sorted(group.attrs.keys()):
        result[key] = _read_attr(group.attrs[key])
    for key in sorted(group.keys()):
        item = group[key]
        if isinstance(item, h5py.Group):
            result[key] = h5_to_dict(item)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _write_value(group: h5py.Group, key: str, value: Any) -> None:
    if isinstance(value, dict):
        sub = group.create_group(key)
        dict_to_h5(sub, value)
    elif isinstance(value, bool):
        group.attrs[key] = np.bool_(value)
    elif isinstance(value, int):
        group.attrs[key] = np.int64(value)
    elif isinstance(value, float):
        group.attrs[key] = np.float64(value)
    elif isinstance(value, str):
        group.attrs[key] = value
    elif isinstance(value, list):
        _write_list(group, key, value)
    else:
        raise TypeError(f"Unsupported type {type(value).__name__!r} for key {key!r}")


def _write_list(group: h5py.Group, key: str, lst: list[Any]) -> None:
    if len(lst) == 0:
        group.attrs.create(key, data=np.array([], dtype=np.float64))
        return

    first = lst[0]
    if isinstance(first, bool):
        group.attrs[key] = np.array(lst, dtype=np.bool_)
    elif isinstance(first, (int, float)):
        group.attrs[key] = np.array(lst)
    elif isinstance(first, str):
        dt = h5py.special_dtype(vlen=str)
        group.attrs.create(key, data=lst, dtype=dt)
    else:
        raise TypeError(
            f"Unsupported type {type(first).__name__!r} in list for key {key!r}"
        )


def _read_attr(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, str):
        return value
    if isinstance(value, np.ndarray):
        return _read_array(value)
    return value


def _read_array(arr: np.ndarray) -> list[Any]:
    if arr.dtype.kind in ("U", "S", "O"):
        return [str(v) for v in arr]
    if arr.dtype == np.bool_:
        return [bool(v) for v in arr]
    return arr.tolist()
