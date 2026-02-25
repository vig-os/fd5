"""fd5.manifest — TOML manifest generation and parsing.

Scans a directory of fd5 HDF5 files, extracts root attributes,
and writes/reads a ``manifest.toml`` index.  See white-paper.md § manifest.toml.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import h5py
import tomli_w

from fd5.h5io import h5_to_dict

_MANIFEST_SCHEMA_VERSION = 1

_EXCLUDED_DATA_ATTRS = frozenset(
    {
        "_schema",
        "_schema_version",
        "content_hash",
        "id_inputs",
        "name",
        "description",
    }
)


def build_manifest(directory: Path) -> dict[str, Any]:
    """Scan ``.h5`` files in *directory* and build a manifest dict.

    Files are iterated lazily via ``Path.glob``.  Dataset-level metadata
    (``study``, ``subject``) is taken from the first file that contains them.
    """
    manifest: dict[str, Any] = {
        "_schema_version": _MANIFEST_SCHEMA_VERSION,
        "dataset_name": directory.name,
    }
    data_entries: list[dict[str, Any]] = []

    for h5_path in sorted(directory.glob("*.h5")):
        with h5py.File(h5_path, "r") as f:
            root_attrs = h5_to_dict(f)

            _extract_dataset_metadata(manifest, f)

            entry = _build_data_entry(root_attrs, h5_path.name)
            data_entries.append(entry)

    manifest["data"] = data_entries
    return manifest


def write_manifest(directory: Path, output_path: Path) -> None:
    """Build a manifest from *directory* and write it as TOML to *output_path*."""
    manifest = build_manifest(directory)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(tomli_w.dumps(manifest).encode())


def read_manifest(path: Path) -> dict[str, Any]:
    """Parse an existing ``manifest.toml`` and return the dict."""
    return tomllib.loads(path.read_text())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_dataset_metadata(manifest: dict[str, Any], f: h5py.File) -> None:
    """Extract study/subject groups from the HDF5 file into the manifest (once)."""
    if "study" not in manifest and "study" in f:
        manifest["study"] = h5_to_dict(f["study"])
    if "subject" not in manifest and "subject" in f:
        manifest["subject"] = h5_to_dict(f["subject"])


def _build_data_entry(root_attrs: dict[str, Any], filename: str) -> dict[str, Any]:
    """Build a single ``[[data]]`` entry from root attributes."""
    entry: dict[str, Any] = {}
    for key, value in root_attrs.items():
        if key not in _EXCLUDED_DATA_ATTRS and not isinstance(value, dict):
            entry[key] = value
    entry["file"] = filename
    return entry
