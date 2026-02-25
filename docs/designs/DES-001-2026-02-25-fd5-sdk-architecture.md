# DES-001 — fd5 SDK Architecture

| Field       | Value                          |
|-------------|--------------------------------|
| ID          | DES-001                        |
| Date        | 2026-02-25                     |
| Status      | Draft                          |
| Epic        | #11                            |

## Overview

This document captures high-level architecture decisions for the fd5 Python SDK.
Each module section describes its public API, storage layout, and rationale.

## `fd5.units` — Physical quantity convention

**Issue:** [#13](../../issues/13)

### Motivation

Every numerical attribute or dataset with physical meaning must carry units
information so that readers (human or automated) can interpret values without
ambiguity. The fd5 format uses two patterns, both inspired by NeXus/OpenPMD
conventions (see [white-paper.md § Units convention](../../white-paper.md#units-convention)).

### Storage layout

**Attributes with units** use a sub-group pattern:

```
<name>/
    attrs: {value: <scalar_or_array>, units: "<str>", unitSI: <float>}
```

Deleting the group deletes everything — no orphaned attrs.
Any sub-group carrying `value` + `units` + `unitSI` is programmatically
identifiable as a physical quantity.

**Datasets with units** carry attrs directly on the dataset:

```
<dataset>
    attrs: {units: "<str>", unitSI: <float>, ...}
```

### Public API

```python
def write_quantity(
    group: h5py.Group,
    name: str,
    value: float | int | list,
    units: str,
    unit_si: float,
) -> h5py.Group:
    """Create a sub-group ``name/`` with value, units, unitSI attrs."""

def read_quantity(
    group: h5py.Group,
    name: str,
) -> tuple[float | int | list, str, float]:
    """Return (value, units, unit_si) from a quantity sub-group."""

def set_dataset_units(
    dataset: h5py.Dataset,
    units: str,
    unit_si: float,
) -> None:
    """Set units and unitSI attrs on an existing dataset."""
```

### Design decisions

1. **Snake-case API, camelCase HDF5 attrs** — Python callers use `unit_si`;
   the HDF5 attribute is stored as `unitSI` to match the NeXus/OpenPMD
   convention from the white paper.
2. **Return a plain tuple** rather than a dataclass — keeps the module a leaf
   with zero internal dependencies. A richer type can wrap this later.
3. **No implicit SI conversion** — the module stores and retrieves; conversion
   is the caller's responsibility (`value_si = value * unit_si`).
