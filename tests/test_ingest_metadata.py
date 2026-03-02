"""Tests for fd5.ingest.metadata — RO-Crate and DataCite metadata import."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from fd5.ingest.metadata import (
    load_datacite_metadata,
    load_metadata,
    load_rocrate_metadata,
)


# ---------------------------------------------------------------------------
# Synthetic RO-Crate fixtures
# ---------------------------------------------------------------------------

ROCRATE_FULL: dict[str, Any] = {
    "@context": "https://w3id.org/ro/crate/1.2/context",
    "@graph": [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "about": {"@id": "./"},
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": "DOGPLET DD01",
            "license": "CC-BY-4.0",
            "description": "Full PET dataset",
            "author": [
                {
                    "@type": "Person",
                    "name": "Jane Doe",
                    "affiliation": "ETH Zurich",
                    "@id": "https://orcid.org/0000-0002-1234-5678",
                },
                {
                    "@type": "Person",
                    "name": "John Smith",
                    "affiliation": "MIT",
                },
            ],
        },
    ],
}

ROCRATE_MINIMAL: dict[str, Any] = {
    "@context": "https://w3id.org/ro/crate/1.2/context",
    "@graph": [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": "Minimal Dataset",
        },
    ],
}

ROCRATE_NO_DATASET: dict[str, Any] = {
    "@context": "https://w3id.org/ro/crate/1.2/context",
    "@graph": [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "about": {"@id": "./"},
        },
    ],
}


def _write_rocrate(path: Path, data: dict[str, Any]) -> Path:
    out = path / "ro-crate-metadata.json"
    out.write_text(json.dumps(data, indent=2))
    return out


# ---------------------------------------------------------------------------
# Synthetic DataCite fixtures
# ---------------------------------------------------------------------------

DATACITE_FULL: dict[str, Any] = {
    "title": "DOGPLET DD01",
    "creators": [
        {"name": "Jane Doe", "affiliation": "ETH Zurich"},
        {"name": "John Smith", "affiliation": "MIT"},
    ],
    "dates": [
        {"date": "2024-07-24", "dateType": "Collected"},
    ],
    "subjects": [
        {"subject": "FDG", "subjectScheme": "Radiotracer"},
    ],
    "resourceType": "Dataset",
}

DATACITE_MINIMAL: dict[str, Any] = {
    "title": "Minimal",
}


def _write_datacite(path: Path, data: dict[str, Any]) -> Path:
    out = path / "datacite.yml"
    out.write_text(yaml.dump(data, default_flow_style=False))
    return out


# ---------------------------------------------------------------------------
# load_rocrate_metadata
# ---------------------------------------------------------------------------


class TestLoadRocrateMetadata:
    def test_extracts_name(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_FULL)
        result = load_rocrate_metadata(f)
        assert result["name"] == "DOGPLET DD01"

    def test_extracts_license(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_FULL)
        result = load_rocrate_metadata(f)
        assert result["license"] == "CC-BY-4.0"

    def test_extracts_description(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_FULL)
        result = load_rocrate_metadata(f)
        assert result["description"] == "Full PET dataset"

    def test_extracts_creators(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_FULL)
        result = load_rocrate_metadata(f)
        creators = result["creators"]
        assert len(creators) == 2
        assert creators[0]["name"] == "Jane Doe"
        assert creators[0]["affiliation"] == "ETH Zurich"
        assert creators[0]["orcid"] == "https://orcid.org/0000-0002-1234-5678"

    def test_creator_without_orcid(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_FULL)
        result = load_rocrate_metadata(f)
        john = result["creators"][1]
        assert john["name"] == "John Smith"
        assert "orcid" not in john

    def test_creator_without_affiliation(self, tmp_path: Path):
        crate = {
            "@context": "https://w3id.org/ro/crate/1.2/context",
            "@graph": [
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "name": "Test",
                    "author": [{"@type": "Person", "name": "Solo Dev"}],
                },
            ],
        }
        f = _write_rocrate(tmp_path, crate)
        result = load_rocrate_metadata(f)
        assert result["creators"][0]["name"] == "Solo Dev"
        assert "affiliation" not in result["creators"][0]

    def test_missing_license_absent_key(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_MINIMAL)
        result = load_rocrate_metadata(f)
        assert "license" not in result

    def test_missing_description_absent_key(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_MINIMAL)
        result = load_rocrate_metadata(f)
        assert "description" not in result

    def test_missing_authors_absent_creators(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_MINIMAL)
        result = load_rocrate_metadata(f)
        assert "creators" not in result

    def test_no_dataset_entity_returns_empty(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_NO_DATASET)
        result = load_rocrate_metadata(f)
        assert result == {}

    def test_returns_dict(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_FULL)
        result = load_rocrate_metadata(f)
        assert isinstance(result, dict)

    def test_result_usable_with_write_study(self, tmp_path: Path):
        """Returned dict keys should match builder.write_study() parameters."""
        f = _write_rocrate(tmp_path, ROCRATE_FULL)
        result = load_rocrate_metadata(f)
        allowed = {"study_type", "license", "name", "description", "creators"}
        assert set(result.keys()) <= allowed

    def test_study_type_not_set(self, tmp_path: Path):
        """RO-Crate doesn't map to study_type, so key should be absent."""
        f = _write_rocrate(tmp_path, ROCRATE_FULL)
        result = load_rocrate_metadata(f)
        assert "study_type" not in result

    def test_empty_author_list(self, tmp_path: Path):
        crate = {
            "@context": "https://w3id.org/ro/crate/1.2/context",
            "@graph": [
                {"@id": "./", "@type": "Dataset", "name": "Test", "author": []},
            ],
        }
        f = _write_rocrate(tmp_path, crate)
        result = load_rocrate_metadata(f)
        assert "creators" not in result

    def test_nonexistent_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_rocrate_metadata(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# load_datacite_metadata
# ---------------------------------------------------------------------------


class TestLoadDataciteMetadata:
    def test_extracts_name_from_title(self, tmp_path: Path):
        f = _write_datacite(tmp_path, DATACITE_FULL)
        result = load_datacite_metadata(f)
        assert result["name"] == "DOGPLET DD01"

    def test_extracts_creators(self, tmp_path: Path):
        f = _write_datacite(tmp_path, DATACITE_FULL)
        result = load_datacite_metadata(f)
        creators = result["creators"]
        assert len(creators) == 2
        assert creators[0]["name"] == "Jane Doe"
        assert creators[0]["affiliation"] == "ETH Zurich"

    def test_extracts_dates(self, tmp_path: Path):
        f = _write_datacite(tmp_path, DATACITE_FULL)
        result = load_datacite_metadata(f)
        assert result["dates"] == [{"date": "2024-07-24", "dateType": "Collected"}]

    def test_extracts_subjects(self, tmp_path: Path):
        f = _write_datacite(tmp_path, DATACITE_FULL)
        result = load_datacite_metadata(f)
        assert result["subjects"] == [
            {"subject": "FDG", "subjectScheme": "Radiotracer"}
        ]

    def test_missing_creators_absent_key(self, tmp_path: Path):
        f = _write_datacite(tmp_path, DATACITE_MINIMAL)
        result = load_datacite_metadata(f)
        assert "creators" not in result

    def test_missing_dates_absent_key(self, tmp_path: Path):
        f = _write_datacite(tmp_path, DATACITE_MINIMAL)
        result = load_datacite_metadata(f)
        assert "dates" not in result

    def test_missing_subjects_absent_key(self, tmp_path: Path):
        f = _write_datacite(tmp_path, DATACITE_MINIMAL)
        result = load_datacite_metadata(f)
        assert "subjects" not in result

    def test_missing_title_absent_name(self, tmp_path: Path):
        f = _write_datacite(tmp_path, {})
        result = load_datacite_metadata(f)
        assert "name" not in result

    def test_returns_dict(self, tmp_path: Path):
        f = _write_datacite(tmp_path, DATACITE_FULL)
        result = load_datacite_metadata(f)
        assert isinstance(result, dict)

    def test_result_keys_subset_of_study_params(self, tmp_path: Path):
        """Keys must be compatible with builder.write_study() + extra metadata."""
        f = _write_datacite(tmp_path, DATACITE_FULL)
        result = load_datacite_metadata(f)
        allowed = {
            "study_type",
            "license",
            "name",
            "description",
            "creators",
            "dates",
            "subjects",
        }
        assert set(result.keys()) <= allowed

    def test_empty_creators_list(self, tmp_path: Path):
        f = _write_datacite(tmp_path, {"title": "Test", "creators": []})
        result = load_datacite_metadata(f)
        assert "creators" not in result

    def test_nonexistent_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_datacite_metadata(tmp_path / "nonexistent.yml")


# ---------------------------------------------------------------------------
# load_metadata (auto-detect)
# ---------------------------------------------------------------------------


class TestLoadMetadata:
    def test_detects_rocrate(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_FULL)
        result = load_metadata(f)
        assert result["name"] == "DOGPLET DD01"
        assert result["license"] == "CC-BY-4.0"

    def test_detects_datacite_yml(self, tmp_path: Path):
        f = _write_datacite(tmp_path, DATACITE_FULL)
        result = load_metadata(f)
        assert result["name"] == "DOGPLET DD01"

    def test_detects_datacite_yaml(self, tmp_path: Path):
        out = tmp_path / "datacite.yaml"
        out.write_text(yaml.dump(DATACITE_FULL, default_flow_style=False))
        result = load_metadata(out)
        assert result["name"] == "DOGPLET DD01"

    def test_generic_json(self, tmp_path: Path):
        data = {"name": "Generic Study", "license": "MIT"}
        f = tmp_path / "meta.json"
        f.write_text(json.dumps(data))
        result = load_metadata(f)
        assert result == data

    def test_generic_yaml(self, tmp_path: Path):
        data = {"name": "YAML Study", "description": "A study from YAML"}
        f = tmp_path / "meta.yml"
        f.write_text(yaml.dump(data))
        result = load_metadata(f)
        assert result == data

    def test_generic_yaml_extension(self, tmp_path: Path):
        data = {"name": "YAML Study"}
        f = tmp_path / "meta.yaml"
        f.write_text(yaml.dump(data))
        result = load_metadata(f)
        assert result == data

    def test_unsupported_extension_raises(self, tmp_path: Path):
        f = tmp_path / "meta.txt"
        f.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported"):
            load_metadata(f)

    def test_nonexistent_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_metadata(tmp_path / "nonexistent.json")

    def test_returns_dict(self, tmp_path: Path):
        f = _write_rocrate(tmp_path, ROCRATE_FULL)
        result = load_metadata(f)
        assert isinstance(result, dict)
