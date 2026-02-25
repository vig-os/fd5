"""fd5.datacite — DataCite metadata export.

Generates ``datacite.yml`` from the manifest and HDF5 metadata.
See white-paper.md § datacite.yml for the spec.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import yaml

from fd5.manifest import read_manifest


def generate(manifest_path: Path) -> dict[str, Any]:
    """Build a DataCite metadata dict from *manifest_path* and sibling HDF5 files.

    Returns a dict ready for YAML serialisation with keys:
    ``title``, ``creators``, ``dates``, ``resourceType``, ``subjects``.
    """
    manifest = read_manifest(manifest_path)
    data_dir = manifest_path.parent

    title = _build_title(manifest)
    creators = _build_creators(manifest)
    dates = _build_dates(manifest)
    subjects = _build_subjects(manifest, data_dir)

    return {
        "title": title,
        "creators": creators,
        "dates": dates,
        "resourceType": "Dataset",
        "subjects": subjects,
    }


def write(manifest_path: Path, output_path: Path) -> None:
    """Generate DataCite metadata and write it as YAML to *output_path*."""
    metadata = generate(manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.dump(
            metadata, default_flow_style=False, sort_keys=False, allow_unicode=True
        )
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_title(manifest: dict[str, Any]) -> str:
    return manifest.get("dataset_name", "Untitled")


def _build_creators(manifest: dict[str, Any]) -> list[dict[str, str]]:
    study = manifest.get("study", {})
    creators_group = study.get("creators", {})
    if not creators_group:
        return []

    result: list[dict[str, str]] = []
    for key in sorted(creators_group):
        creator = creators_group[key]
        entry: dict[str, str] = {"name": creator["name"]}
        if "affiliation" in creator:
            entry["affiliation"] = creator["affiliation"]
        result.append(entry)
    return result


def _build_dates(manifest: dict[str, Any]) -> list[dict[str, str]]:
    data = manifest.get("data", [])
    if not data:
        return []

    timestamps = [entry["timestamp"] for entry in data if "timestamp" in entry]
    if not timestamps:
        return []

    earliest = min(timestamps)
    date_str = earliest[:10]  # "YYYY-MM-DD" prefix from ISO 8601
    return [{"date": date_str, "dateType": "Collected"}]


def _build_subjects(manifest: dict[str, Any], data_dir: Path) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    subjects: list[dict[str, str]] = []

    for entry in manifest.get("data", []):
        scan_type = entry.get("scan_type")
        scheme = entry.get("scan_type_vocabulary")
        if scan_type and scheme:
            pair = (scan_type, scheme)
            if pair not in seen:
                seen.add(pair)
                subjects.append({"subject": scan_type, "subjectScheme": scheme})

        h5_file = data_dir / entry.get("file", "")
        if h5_file.is_file():
            _collect_tracer_subjects(h5_file, seen, subjects)

    return subjects


def _collect_tracer_subjects(
    h5_path: Path,
    seen: set[tuple[str, str]],
    subjects: list[dict[str, str]],
) -> None:
    try:
        with h5py.File(h5_path, "r") as f:
            tracer_group = f.get("metadata/pet/tracer")
            if tracer_group is None:
                return
            name = tracer_group.attrs.get("name")
            if name is None:
                return
            if isinstance(name, bytes):
                name = name.decode("utf-8")
            pair = (name, "Radiotracer")
            if pair not in seen:
                seen.add(pair)
                subjects.append({"subject": name, "subjectScheme": "Radiotracer"})
    except Exception:
        return
