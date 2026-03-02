"""Physical units convention helpers.

Implements the value/units/unitSI sub-group pattern for attributes and
the units/unitSI attribute pattern for datasets as defined in the fd5
white paper (see white-paper.md § Units convention).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import h5py
    import numpy as np

type Scalar = int | float
type QuantityValue = Scalar | list[Scalar] | np.ndarray


def write_quantity(
    group: h5py.Group,
    name: str,
    value: QuantityValue,
    units: str,
    unit_si: float,
) -> None:
    """Create a sub-group with ``value``, ``units``, and ``unitSI`` attrs.

    If a sub-group with *name* already exists it is replaced.
    """
    if name in group:
        del group[name]
    sub = group.create_group(name)
    sub.attrs["value"] = value
    sub.attrs["units"] = units
    sub.attrs["unitSI"] = unit_si


def read_quantity(
    group: h5py.Group,
    name: str,
) -> tuple[QuantityValue, str, float]:
    """Read a physical quantity sub-group.

    Returns:
        ``(value, units, unit_si)`` tuple.

    Raises:
        KeyError: If *name* does not exist in *group*.
    """
    sub = group[name]
    return sub.attrs["value"], sub.attrs["units"], sub.attrs["unitSI"]


def set_dataset_units(
    dataset: h5py.Dataset,
    units: str,
    unit_si: float,
) -> None:
    """Set ``units`` and ``unitSI`` attributes on a dataset."""
    dataset.attrs["units"] = units
    dataset.attrs["unitSI"] = unit_si
