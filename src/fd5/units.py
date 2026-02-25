"""Physical quantity convention helpers for HDF5 files.

Implements the value/units/unitSI sub-group pattern for attributes
and the units/unitSI attribute pattern for datasets. See
`docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5units--physical-quantity-convention`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import h5py


def write_quantity(
    group: h5py.Group,
    name: str,
    value: float | int | list,
    units: str,
    unit_si: float,
) -> h5py.Group:
    """Create a sub-group *name/* with ``value``, ``units``, ``unitSI`` attrs.

    Parameters
    ----------
    group:
        Parent HDF5 group.
    name:
        Name for the new quantity sub-group.
    value:
        Scalar, integer, or array-like value.
    units:
        Human-readable unit string (e.g. ``"mm"``, ``"s"``, ``"MBq"``).
    unit_si:
        Numeric conversion factor to SI base units.

    Returns
    -------
    h5py.Group
        The newly created sub-group.

    Raises
    ------
    ValueError
        If *name* already exists in *group*.
    """
    if name in group:
        msg = f"Quantity '{name}' already exists in {group.name}"
        raise ValueError(msg)

    sub = group.create_group(name)
    sub.attrs["value"] = value
    sub.attrs["units"] = units
    sub.attrs["unitSI"] = unit_si
    return sub


def read_quantity(
    group: h5py.Group,
    name: str,
) -> tuple[float | int | list, str, float]:
    """Read a physical quantity from a sub-group.

    Parameters
    ----------
    group:
        Parent HDF5 group containing the quantity sub-group.
    name:
        Name of the quantity sub-group.

    Returns
    -------
    tuple[float | int | list, str, float]
        ``(value, units, unit_si)``

    Raises
    ------
    KeyError
        If *name* does not exist or lacks required attrs.
    """
    sub = group[name]
    return sub.attrs["value"], str(sub.attrs["units"]), float(sub.attrs["unitSI"])


def set_dataset_units(
    dataset: h5py.Dataset,
    units: str,
    unit_si: float,
) -> None:
    """Set ``units`` and ``unitSI`` attributes on a dataset.

    Parameters
    ----------
    dataset:
        An existing HDF5 dataset.
    units:
        Human-readable unit string.
    unit_si:
        Numeric conversion factor to SI base units.
    """
    dataset.attrs["units"] = units
    dataset.attrs["unitSI"] = unit_si
