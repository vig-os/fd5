"""Tests for fd5.rocrate — RO-Crate JSON-LD generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import pytest

from fd5.h5io import dict_to_h5
from fd5.provenance import write_ingest, write_sources


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_h5(
    path: Path,
    root_attrs: dict[str, Any],
    groups: dict[str, dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    ingest: dict[str, str] | None = None,
) -> None:
    with h5py.File(path, "w") as f:
        dict_to_h5(f, root_attrs)
        if groups:
            for name, attrs in groups.items():
                g = f.create_group(name)
                dict_to_h5(g, attrs)
        if sources:
            write_sources(f, sources)
        if ingest:
            write_ingest(f, **ingest)


def _graph_by_id(crate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index @graph entities by @id for convenient lookup."""
    return {e["@id"]: e for e in crate["@graph"]}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CREATOR_JANE = {
    "name": "Jane Doe",
    "affiliation": "ETH Zurich",
    "orcid": "https://orcid.org/0000-0002-1234-5678",
}

CREATOR_JOHN = {
    "name": "John Smith",
    "affiliation": "MIT",
    "orcid": "https://orcid.org/0000-0003-9999-0000",
}


@pytest.fixture()
def full_dir(tmp_path: Path) -> Path:
    """Directory with two HDF5 files, study metadata, provenance, and sources."""
    _create_h5(
        tmp_path / "recon-aabb1122.h5",
        root_attrs={
            "_schema_version": 1,
            "product": "recon",
            "id": "sha256:aabb112233445566",
            "content_hash": "sha256:deadbeef",
            "timestamp": "2024-07-24T19:06:10+02:00",
        },
        groups={
            "study": {
                "license": "CC-BY-4.0",
                "name": "DOGPLET DD01",
                "creators": {
                    "0": CREATOR_JANE,
                    "1": CREATOR_JOHN,
                },
            },
        },
        sources=[
            {
                "name": "listmode",
                "id": "sha256:src111111",
                "product": "listmode",
                "file": "listmode-src11111.h5",
                "content_hash": "sha256:src111111",
                "role": "primary",
                "description": "Source listmode",
            },
        ],
        ingest={
            "tool": "fd5-imaging-ingest",
            "version": "0.3.0",
            "timestamp": "2024-07-25T08:00:00Z",
        },
    )
    _create_h5(
        tmp_path / "roi-ccdd3344.h5",
        root_attrs={
            "_schema_version": 1,
            "product": "roi",
            "id": "sha256:ccdd334455667788",
            "content_hash": "sha256:cafebabe",
            "timestamp": "2026-01-15T10:30:00+01:00",
        },
        groups={
            "study": {
                "license": "CC-BY-4.0",
                "name": "DOGPLET DD01",
                "creators": {
                    "0": CREATOR_JANE,
                    "1": CREATOR_JOHN,
                },
            },
        },
    )
    return tmp_path


@pytest.fixture()
def minimal_dir(tmp_path: Path) -> Path:
    """Directory with a single HDF5 file, no study/sources/provenance."""
    _create_h5(
        tmp_path / "sim-11223344.h5",
        root_attrs={
            "_schema_version": 1,
            "product": "sim",
            "id": "sha256:1122334455667788",
            "content_hash": "sha256:00000000",
            "timestamp": "2025-06-01T12:00:00Z",
        },
    )
    return tmp_path


@pytest.fixture()
def empty_dir(tmp_path: Path) -> Path:
    """Empty directory with no HDF5 files."""
    return tmp_path


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_returns_dict(self, full_dir: Path):
        from fd5.rocrate import generate

        result = generate(full_dir)
        assert isinstance(result, dict)

    def test_context(self, full_dir: Path):
        from fd5.rocrate import generate

        result = generate(full_dir)
        assert result["@context"] == "https://w3id.org/ro/crate/1.2/context"

    def test_graph_is_list(self, full_dir: Path):
        from fd5.rocrate import generate

        result = generate(full_dir)
        assert isinstance(result["@graph"], list)

    def test_metadata_descriptor(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        desc = entities["ro-crate-metadata.json"]
        assert desc["@type"] == "CreativeWork"
        assert desc["about"] == {"@id": "./"}
        assert desc["conformsTo"] == {"@id": "https://w3id.org/ro/crate/1.2"}

    def test_root_dataset_entity(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        root = entities["./"]
        assert root["@type"] == "Dataset"

    def test_license_mapped(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        root = entities["./"]
        assert root["license"] == "CC-BY-4.0"

    def test_dataset_name(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        root = entities["./"]
        assert root["name"] == "DOGPLET DD01"

    def test_author_persons(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        root = entities["./"]
        authors = root["author"]
        assert len(authors) == 2
        jane = authors[0]
        assert jane["@type"] == "Person"
        assert jane["name"] == "Jane Doe"
        assert jane["affiliation"] == "ETH Zurich"
        assert jane["@id"] == "https://orcid.org/0000-0002-1234-5678"

    def test_has_part_lists_files(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        root = entities["./"]
        ids = {p["@id"] for p in root["hasPart"]}
        assert "recon-aabb1122.h5" in ids
        assert "roi-ccdd3344.h5" in ids

    def test_file_entities(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        recon = entities["recon-aabb1122.h5"]
        assert recon["@type"] == "File"
        assert recon["encodingFormat"] == "application/x-hdf5"

    def test_file_date_created(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        recon = entities["recon-aabb1122.h5"]
        assert recon["dateCreated"] == "2024-07-24T19:06:10+02:00"

    def test_file_identifier_property_value(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        recon = entities["recon-aabb1122.h5"]
        ident = recon["identifier"]
        assert ident["@type"] == "PropertyValue"
        assert ident["propertyID"] == "sha256"
        assert ident["value"] == "sha256:aabb112233445566"

    def test_is_based_on_from_sources(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        recon = entities["recon-aabb1122.h5"]
        assert recon["isBasedOn"] == [{"@id": "listmode-src11111.h5"}]

    def test_create_action_from_ingest(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        actions = [e for e in entities.values() if e.get("@type") == "CreateAction"]
        assert len(actions) >= 1
        action = actions[0]
        assert action["result"] == {"@id": "recon-aabb1122.h5"}
        instrument = action["instrument"]
        assert instrument["@type"] == "SoftwareApplication"
        assert instrument["name"] == "fd5-imaging-ingest"
        assert instrument["version"] == "0.3.0"

    def test_no_sources_no_is_based_on(self, full_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(full_dir))
        roi = entities["roi-ccdd3344.h5"]
        assert "isBasedOn" not in roi

    def test_no_ingest_no_create_action(self, minimal_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(minimal_dir))
        actions = [e for e in entities.values() if e.get("@type") == "CreateAction"]
        assert len(actions) == 0


class TestGenerateMinimal:
    def test_no_study_no_license(self, minimal_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(minimal_dir))
        root = entities["./"]
        assert "license" not in root

    def test_no_study_no_author(self, minimal_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(minimal_dir))
        root = entities["./"]
        assert "author" not in root

    def test_name_falls_back_to_dir(self, minimal_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(minimal_dir))
        root = entities["./"]
        assert root["name"] == minimal_dir.name

    def test_single_file_entity(self, minimal_dir: Path):
        from fd5.rocrate import generate

        entities = _graph_by_id(generate(minimal_dir))
        assert "sim-11223344.h5" in entities

    def test_empty_dir(self, empty_dir: Path):
        from fd5.rocrate import generate

        result = generate(empty_dir)
        entities = _graph_by_id(result)
        root = entities["./"]
        assert root["hasPart"] == []


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------


class TestWrite:
    def test_creates_file(self, full_dir: Path):
        from fd5.rocrate import write

        write(full_dir)
        out = full_dir / "ro-crate-metadata.json"
        assert out.exists()

    def test_output_is_valid_json(self, full_dir: Path):
        from fd5.rocrate import write

        write(full_dir)
        parsed = json.loads((full_dir / "ro-crate-metadata.json").read_text())
        assert "@context" in parsed

    def test_custom_output_path(self, full_dir: Path, tmp_path: Path):
        from fd5.rocrate import write

        out = tmp_path / "custom" / "crate.json"
        write(full_dir, out)
        assert out.exists()
        parsed = json.loads(out.read_text())
        assert "@graph" in parsed


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_creator_without_orcid(self, tmp_path: Path):
        """Creators missing ORCID should still appear as Person, without @id."""
        from fd5.rocrate import generate

        _create_h5(
            tmp_path / "recon-aaa.h5",
            root_attrs={
                "_schema_version": 1,
                "product": "recon",
                "id": "sha256:aaa",
                "content_hash": "sha256:bbb",
                "timestamp": "2025-01-01T00:00:00Z",
            },
            groups={
                "study": {
                    "license": "CC0-1.0",
                    "name": "Test",
                    "creators": {
                        "0": {"name": "No Orcid Person", "affiliation": "Somewhere"},
                    },
                },
            },
        )
        entities = _graph_by_id(generate(tmp_path))
        root = entities["./"]
        person = root["author"][0]
        assert person["@type"] == "Person"
        assert person["name"] == "No Orcid Person"
        assert "@id" not in person

    def test_creator_without_affiliation(self, tmp_path: Path):
        from fd5.rocrate import generate

        _create_h5(
            tmp_path / "recon-aaa.h5",
            root_attrs={
                "_schema_version": 1,
                "product": "recon",
                "id": "sha256:aaa",
                "content_hash": "sha256:bbb",
                "timestamp": "2025-01-01T00:00:00Z",
            },
            groups={
                "study": {
                    "license": "CC0-1.0",
                    "name": "Test",
                    "creators": {
                        "0": {"name": "Solo Dev"},
                    },
                },
            },
        )
        entities = _graph_by_id(generate(tmp_path))
        person = entities["./"]["author"][0]
        assert person["name"] == "Solo Dev"
        assert "affiliation" not in person

    def test_multiple_sources(self, tmp_path: Path):
        """File with multiple sources should produce multiple isBasedOn refs."""
        from fd5.rocrate import generate

        _create_h5(
            tmp_path / "recon-multi.h5",
            root_attrs={
                "_schema_version": 1,
                "product": "recon",
                "id": "sha256:multi",
                "content_hash": "sha256:multi",
                "timestamp": "2025-01-01T00:00:00Z",
            },
            sources=[
                {
                    "name": "listmode",
                    "id": "sha256:src1",
                    "product": "listmode",
                    "file": "listmode-src1.h5",
                    "content_hash": "sha256:src1",
                    "role": "primary",
                    "description": "Source 1",
                },
                {
                    "name": "ctac",
                    "id": "sha256:src2",
                    "product": "ctac",
                    "file": "ctac-src2.h5",
                    "content_hash": "sha256:src2",
                    "role": "attenuation",
                    "description": "Source 2",
                },
            ],
        )
        entities = _graph_by_id(generate(tmp_path))
        recon = entities["recon-multi.h5"]
        refs = recon["isBasedOn"]
        files = {r["@id"] for r in refs}
        assert files == {"listmode-src1.h5", "ctac-src2.h5"}
