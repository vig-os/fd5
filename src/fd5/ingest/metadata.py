"""fd5.ingest.metadata — RO-Crate and DataCite metadata import.

Reads existing metadata files (RO-Crate JSON-LD, DataCite YAML, or
generic structured metadata) and returns dicts suitable for
:meth:`fd5.create.Fd5Builder.write_study`.

This is the *inverse* of :mod:`fd5.rocrate` and :mod:`fd5.datacite`
exports: instead of generating metadata from fd5 files, we consume
external metadata to populate fd5 files during ingest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_rocrate_metadata(rocrate_path: Path) -> dict[str, Any]:
    """Extract fd5-compatible study metadata from an RO-Crate JSON-LD file.

    Returns a dict with possible keys: ``name``, ``license``,
    ``description``, ``creators``.  Missing fields in the source are
    omitted (no ``KeyError``).
    """
    rocrate_path = Path(rocrate_path)
    crate = json.loads(rocrate_path.read_text(encoding="utf-8"))

    dataset = _find_rocrate_dataset(crate)
    if dataset is None:
        return {}

    result: dict[str, Any] = {}

    if "name" in dataset:
        result["name"] = dataset["name"]
    if "license" in dataset:
        result["license"] = dataset["license"]
    if "description" in dataset:
        result["description"] = dataset["description"]

    creators = _extract_rocrate_creators(dataset)
    if creators:
        result["creators"] = creators

    return result


def load_datacite_metadata(datacite_path: Path) -> dict[str, Any]:
    """Extract fd5-compatible study metadata from a DataCite YAML file.

    Returns a dict with possible keys: ``name``, ``creators``,
    ``dates``, ``subjects``.  Missing fields in the source are omitted.
    """
    datacite_path = Path(datacite_path)
    data = yaml.safe_load(datacite_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}

    result: dict[str, Any] = {}

    if "title" in data:
        result["name"] = data["title"]

    creators = data.get("creators")
    if creators:
        result["creators"] = [_normalise_datacite_creator(c) for c in creators]

    dates = data.get("dates")
    if dates:
        result["dates"] = dates

    subjects = data.get("subjects")
    if subjects:
        result["subjects"] = subjects

    return result


def load_metadata(path: Path) -> dict[str, Any]:
    """Auto-detect metadata format and extract fd5-compatible metadata.

    Detection is filename-based:
    - ``ro-crate-metadata.json`` → RO-Crate
    - ``datacite.yml`` / ``datacite.yaml`` → DataCite
    - other ``.json`` → generic JSON pass-through
    - other ``.yml`` / ``.yaml`` → generic YAML pass-through

    Raises :class:`ValueError` for unsupported extensions and
    :class:`FileNotFoundError` for missing files.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.name == "ro-crate-metadata.json":
        return load_rocrate_metadata(path)

    if path.name in {"datacite.yml", "datacite.yaml"}:
        return load_datacite_metadata(path)

    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix in {".yml", ".yaml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    msg = f"Unsupported metadata format: {path.name}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_rocrate_dataset(crate: dict[str, Any]) -> dict[str, Any] | None:
    """Return the root Dataset entity from an RO-Crate ``@graph``."""
    for entity in crate.get("@graph", []):
        if entity.get("@id") == "./" and entity.get("@type") == "Dataset":
            return entity
    return None


def _extract_rocrate_creators(
    dataset: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert RO-Crate ``author`` Person entities to fd5 creator dicts."""
    authors = dataset.get("author")
    if not authors:
        return []

    creators: list[dict[str, Any]] = []
    for person in authors:
        creator: dict[str, Any] = {"name": person["name"]}
        if "affiliation" in person:
            creator["affiliation"] = person["affiliation"]
        if "@id" in person and person["@id"].startswith("https://orcid.org/"):
            creator["orcid"] = person["@id"]
        creators.append(creator)
    return creators


def _normalise_datacite_creator(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single DataCite creator entry."""
    result: dict[str, Any] = {"name": raw["name"]}
    if "affiliation" in raw:
        result["affiliation"] = raw["affiliation"]
    return result
