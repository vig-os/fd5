"""fd5.provenance — writers for sources/ and provenance/ groups.

Implements the provenance DAG (sources/ with HDF5 external links) and
original-file tracking (provenance/original_files compound dataset,
provenance/ingest/ attrs) per white-paper.md §§ sources/ group, provenance/ group.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Union

import h5py
import numpy as np

from fd5._types import SourceRecord
from fd5.h5io import dict_to_h5

_SOURCES_DESCRIPTION = "Data products this file was derived from"
_PROVENANCE_DESCRIPTION = (
    "Provenance of the original source files ingested into this product"
)
_INGEST_DESCRIPTION = "Ingest pipeline that created this file"

_SOURCE_ATTR_KEYS = ("id", "product", "file", "content_hash", "role", "description")


def _normalise_source(src: Union[SourceRecord, dict[str, Any]]) -> dict[str, Any]:
    """Convert a *SourceRecord* or plain dict into a uniform dict."""
    if dataclasses.is_dataclass(src) and not isinstance(src, type):
        return dataclasses.asdict(src)  # type: ignore[arg-type]
    return src  # type: ignore[return-value]


def write_sources(
    file: h5py.File,
    sources: list[Union[SourceRecord, dict[str, Any]]],
) -> None:
    """Create ``sources/`` group with per-source sub-groups, attrs, and external links.

    Each element in *sources* may be a :class:`~fd5._types.SourceRecord`
    or a plain dict.  Dicts must contain ``name`` (used as the sub-group key)
    plus ``id``, ``product``, ``file``, ``content_hash``, ``role``, and
    ``description``.  The ``file`` value is used as a relative-path HDF5
    external link targeting ``"/"``.
    """
    if "sources" in file:
        raise ValueError("sources/ group already exists")

    grp = file.create_group("sources")
    grp.attrs["description"] = _SOURCES_DESCRIPTION

    for src in sources:
        d = _normalise_source(src)
        name = d["name"]
        attrs = {k: d[k] for k in _SOURCE_ATTR_KEYS}
        sub = grp.create_group(name)
        dict_to_h5(sub, attrs)
        sub["link"] = h5py.ExternalLink(d["file"], "/")


def write_original_files(
    file: h5py.File,
    records: list[dict[str, Any]],
) -> None:
    """Create ``provenance/original_files`` compound dataset.

    Each dict in *records* must contain ``path`` (str), ``sha256`` (str),
    and ``size_bytes`` (int).
    """
    prov = _ensure_provenance(file)

    if "original_files" in prov:
        raise ValueError("provenance/original_files already exists")

    dt = np.dtype(
        [
            ("path", h5py.string_dtype()),
            ("sha256", h5py.string_dtype()),
            ("size_bytes", np.int64),
        ]
    )

    if len(records) == 0:
        prov.create_dataset("original_files", shape=(0,), dtype=dt)
        return

    data = np.array(
        [(r["path"], r["sha256"], r["size_bytes"]) for r in records],
        dtype=dt,
    )
    prov.create_dataset("original_files", data=data)


def write_ingest(
    file: h5py.File,
    *,
    tool: str,
    version: str,
    timestamp: str,
) -> None:
    """Create ``provenance/ingest/`` group with tool, version, timestamp attrs."""
    prov = _ensure_provenance(file)

    if "ingest" in prov:
        raise ValueError("provenance/ingest/ already exists")

    ingest = prov.create_group("ingest")
    dict_to_h5(
        ingest,
        {
            "description": _INGEST_DESCRIPTION,
            "timestamp": timestamp,
            "tool": tool,
            "tool_version": version,
        },
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_provenance(file: h5py.File) -> h5py.Group:
    """Return the ``provenance/`` group, creating it if absent."""
    if "provenance" not in file:
        grp = file.create_group("provenance")
        grp.attrs["description"] = _PROVENANCE_DESCRIPTION
        return grp
    return file["provenance"]
