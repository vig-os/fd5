"""fd5.rocrate — RO-Crate 1.2 JSON-LD generation.

Generates ``ro-crate-metadata.json`` from a directory of fd5 HDF5 files.
Maps fd5 vocabulary to Schema.org terms per white-paper.md § ro-crate-metadata.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py

from fd5.h5io import h5_to_dict

_ROCRATE_CONTEXT = "https://w3id.org/ro/crate/1.2/context"
_ROCRATE_CONFORMSTO = "https://w3id.org/ro/crate/1.2"
_HDF5_MEDIA_TYPE = "application/x-hdf5"


def generate(directory: Path) -> dict[str, Any]:
    """Build an RO-Crate JSON-LD dict from fd5 HDF5 files in *directory*."""
    graph: list[dict[str, Any]] = []
    graph.append(_metadata_descriptor())

    file_entities: list[dict[str, Any]] = []
    study: dict[str, Any] | None = None

    for h5_path in sorted(directory.glob("*.h5")):
        with h5py.File(h5_path, "r") as f:
            root_attrs = _safe_root_attrs(f)

            if study is None and "study" in f:
                study = h5_to_dict(f["study"])

            entity = _file_entity(h5_path.name, root_attrs, f)
            _build_create_action(h5_path.name, f, graph)
            file_entities.append(entity)

    root_dataset = _root_dataset(directory.name, study, file_entities)
    graph.append(root_dataset)
    graph.extend(file_entities)

    return {"@context": _ROCRATE_CONTEXT, "@graph": graph}


def write(directory: Path, output_path: Path | None = None) -> None:
    """Generate RO-Crate JSON-LD and write it to *output_path*.

    Defaults to ``<directory>/ro-crate-metadata.json``.
    """
    crate = generate(directory)
    out = output_path or directory / "ro-crate-metadata.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(crate, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_root_attrs(f: h5py.File) -> dict[str, Any]:
    """Read root-level HDF5 attributes without recursing into groups.

    Avoids following external links in sources/ which may be unresolvable.
    """
    from fd5.h5io import _read_attr

    result: dict[str, Any] = {}
    for key in sorted(f.attrs.keys()):
        result[key] = _read_attr(f.attrs[key])
    return result


def _metadata_descriptor() -> dict[str, Any]:
    return {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "about": {"@id": "./"},
        "conformsTo": {"@id": _ROCRATE_CONFORMSTO},
    }


def _root_dataset(
    dir_name: str,
    study: dict[str, Any] | None,
    file_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    root: dict[str, Any] = {
        "@id": "./",
        "@type": "Dataset",
        "hasPart": [{"@id": e["@id"]} for e in file_entities],
    }

    if study:
        root["name"] = study.get("name", dir_name)
        if "license" in study:
            root["license"] = study["license"]
        authors = _build_authors(study)
        if authors:
            root["author"] = authors
    else:
        root["name"] = dir_name

    return root


def _build_authors(study: dict[str, Any]) -> list[dict[str, Any]]:
    creators = study.get("creators")
    if not creators or not isinstance(creators, dict):
        return []

    authors: list[dict[str, Any]] = []
    for key in sorted(creators.keys()):
        c = creators[key]
        if not isinstance(c, dict):
            continue
        person: dict[str, Any] = {"@type": "Person", "name": c["name"]}
        if "affiliation" in c:
            person["affiliation"] = c["affiliation"]
        if "orcid" in c:
            person["@id"] = c["orcid"]
        authors.append(person)
    return authors


def _file_entity(
    filename: str,
    root_attrs: dict[str, Any],
    f: h5py.File,
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "@id": filename,
        "@type": "File",
        "encodingFormat": _HDF5_MEDIA_TYPE,
    }

    if "timestamp" in root_attrs:
        entity["dateCreated"] = root_attrs["timestamp"]

    if "id" in root_attrs:
        entity["identifier"] = {
            "@type": "PropertyValue",
            "propertyID": "sha256",
            "value": root_attrs["id"],
        }

    sources_refs = _build_is_based_on(f)
    if sources_refs:
        entity["isBasedOn"] = sources_refs

    return entity


def _build_is_based_on(f: h5py.File) -> list[dict[str, str]]:
    if "sources" not in f:
        return []
    refs: list[dict[str, str]] = []
    sources_grp = f["sources"]
    for key in sorted(sources_grp.keys()):
        item = sources_grp[key]
        if isinstance(item, h5py.Group) and "file" in item.attrs:
            refs.append({"@id": str(item.attrs["file"])})
    return refs


def _build_create_action(
    filename: str,
    f: h5py.File,
    graph: list[dict[str, Any]],
) -> None:
    if "provenance" not in f or "ingest" not in f["provenance"]:
        return
    ingest = h5_to_dict(f["provenance/ingest"])
    action: dict[str, Any] = {
        "@id": f"#ingest-{filename}",
        "@type": "CreateAction",
        "result": {"@id": filename},
        "instrument": {
            "@type": "SoftwareApplication",
            "name": ingest.get("tool", "unknown"),
            "version": ingest.get("tool_version", "unknown"),
        },
    }
    if "timestamp" in ingest:
        action["endTime"] = ingest["timestamp"]
    graph.append(action)
