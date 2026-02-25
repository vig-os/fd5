"""fd5.datalad — DataLad integration hooks.

Provides metadata extraction in DataLad-compatible format and optional
registration of fd5 files with DataLad datasets.  Gracefully degrades
when DataLad is not installed (datalad is an optional dependency).

See issue #92 and white-paper § Scope and Non-Goals (DataLad integration).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py

from fd5.h5io import h5_to_dict


def _has_datalad() -> bool:
    """Return True if datalad is importable."""
    try:
        import datalad  # noqa: F401

        return True
    except ImportError:
        return False


def extract_metadata(path: str | Path) -> dict[str, Any]:
    """Read an fd5 HDF5 file and return metadata in DataLad-compatible format.

    Returns a dict with keys: ``title``, ``creators``, ``id``, ``product``,
    ``timestamp``, ``content_hash``.  Missing attributes are omitted.
    """
    path = Path(path)
    metadata: dict[str, Any] = {}

    with h5py.File(path, "r") as f:
        root_attrs = _safe_root_attrs(f)

        if "product" in root_attrs:
            metadata["product"] = root_attrs["product"]
        if "id" in root_attrs:
            metadata["id"] = root_attrs["id"]
        if "timestamp" in root_attrs:
            metadata["timestamp"] = root_attrs["timestamp"]
        if "content_hash" in root_attrs:
            metadata["content_hash"] = root_attrs["content_hash"]

        title = root_attrs.get("name", path.stem)
        metadata["title"] = title

        creators = _extract_creators(f)
        if creators:
            metadata["creators"] = creators

    return metadata


def register_with_datalad(
    path: str | Path, dataset_path: str | Path | None = None
) -> dict[str, Any]:
    """Register an fd5 file with a DataLad dataset.

    If *dataset_path* is ``None``, uses the parent directory of *path*.

    Returns a dict with ``status``, ``path``, and ``metadata`` on success.

    Raises ``ImportError`` if datalad is not installed.
    """
    if not _has_datalad():
        raise ImportError(
            "datalad is not installed. Install it with: pip install datalad"
        )

    import importlib

    dl_api = importlib.import_module("datalad.api")

    path = Path(path)
    dataset_path = Path(dataset_path) if dataset_path else path.parent

    ds = dl_api.Dataset(str(dataset_path))
    ds.save(str(path), message=f"Register fd5 file: {path.name}")

    metadata = extract_metadata(path)

    return {
        "status": "ok",
        "path": str(path),
        "dataset": str(dataset_path),
        "metadata": metadata,
    }


def _safe_root_attrs(f: h5py.File) -> dict[str, Any]:
    """Read root-level HDF5 attributes using fd5.h5io helpers."""
    from fd5.h5io import _read_attr

    result: dict[str, Any] = {}
    for key in sorted(f.attrs.keys()):
        result[key] = _read_attr(f.attrs[key])
    return result


def _extract_creators(f: h5py.File) -> list[dict[str, str]]:
    """Extract creator metadata from study group if present."""
    if "study" not in f:
        return []

    study = h5_to_dict(f["study"])
    creators_group = study.get("creators")
    if not creators_group or not isinstance(creators_group, dict):
        return []

    creators: list[dict[str, str]] = []
    for key in sorted(creators_group.keys()):
        c = creators_group[key]
        if not isinstance(c, dict):
            continue
        entry: dict[str, str] = {"name": c["name"]}
        if "affiliation" in c:
            entry["affiliation"] = c["affiliation"]
        if "orcid" in c:
            entry["orcid"] = c["orcid"]
        creators.append(entry)
    return creators
