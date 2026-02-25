# DES-001 — fd5 SDK Architecture

| Field   | Value                    |
|---------|--------------------------|
| ID      | DES-001                  |
| Date    | 2026-02-25               |
| Status  | Draft                    |
| Epic    | #11                      |

## Overview

This document describes the module layout and public API surface of the `fd5`
Python SDK.  Each section maps to one importable sub-module under `src/fd5/`.

## fd5.naming — Filename Generation

### Purpose

Generate deterministic, human-scannable HDF5 filenames that follow the
convention defined in [white-paper.md § File Naming Convention](../../white-paper.md#file-naming-convention):

```
YYYY-MM-DD_HH-MM-SS_<product>-<id>_<descriptors>.h5
```

### Public API

```python
def generate_filename(
    product: str,
    id_hash: str,
    timestamp: datetime | None = None,
    descriptors: Sequence[str] = (),
) -> str: ...
```

#### Parameters

| Parameter     | Type                    | Description |
|---------------|-------------------------|-------------|
| `product`     | `str`                   | Domain-defined product type (e.g. `recon`, `listmode`, `sim`). |
| `id_hash`     | `str`                   | Full identity hash with algorithm prefix, e.g. `"sha256:a1b2c3d4e5f6..."`. Only the first 8 hex chars after the prefix appear in the filename. |
| `timestamp`   | `datetime \| None`      | Acquisition/creation timestamp. When `None`, the datetime prefix is omitted (simulations, synthetic data, calibration). |
| `descriptors` | `Sequence[str]`         | Freeform human-readable labels. Joined with underscores. |

#### Returns

A filename string ending in `.h5`.

#### Rules

1. Timestamp, when present, formatted as `YYYY-MM-DD_HH-MM-SS`.
2. `id_hash` is split on `:` and the hex portion truncated to 8 characters.
3. Descriptors are joined with `_`.
4. Products without a timestamp omit the datetime prefix entirely (no leading
   underscore).

#### Examples

```
generate_filename("recon", "sha256:87f032f6abc...", datetime(2024,7,24,18,14,0), ["ct","thorax","dlir"])
→ "2024-07-24_18-14-00_recon-87f032f6_ct_thorax_dlir.h5"

generate_filename("sim", "sha256:xyz99999...", None, ["pet","nema","gate"])
→ "sim-xyz99999_pet_nema_gate.h5"
```

### Design Decisions

- **Stdlib only** — no external dependencies; uses `datetime.strftime`.
- **Leaf module** — depends on nothing else in `fd5`.
- **Filename is convenience, not identity** — the full hash lives inside the
  HDF5 file.  See [white-paper.md](../../white-paper.md#file-naming-convention).
