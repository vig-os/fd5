"""Tests for fd5.datacite — generate and write DataCite metadata."""

from __future__ import annotations

from pathlib import Path

import h5py
import pytest
import yaml

from fd5.datacite import generate, write


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manifest_path(tmp_path: Path) -> Path:
    """Create a manifest.toml with study/creators and data entries."""
    toml_text = """\
_schema_version = 1
dataset_name = "dd01"

[study]
type = "clinical"
license = "CC-BY-4.0"

[study.creators.creator_0]
name = "Jane Doe"
affiliation = "ETH Zurich"
orcid = "https://orcid.org/0000-0002-1234-5678"
role = "principal_investigator"

[study.creators.creator_1]
name = "John Smith"
affiliation = "University Hospital Zurich"
role = "data_collection"

[subject]
species = "human"
birth_date = "1959-03-15"

[[data]]
product = "recon"
id = "sha256:aabb1122"
file = "recon-aabb1122.h5"
scan_type = "pet"
scan_type_vocabulary = "DICOM Modality"
timestamp = "2024-07-24T19:06:10+02:00"

[[data]]
product = "recon"
id = "sha256:ccdd3344"
file = "recon-ccdd3344.h5"
scan_type = "ct"
scan_type_vocabulary = "DICOM Modality"
timestamp = "2024-07-25T10:00:00+02:00"
"""
    path = tmp_path / "manifest.toml"
    path.write_text(toml_text)

    _create_h5_with_tracer(
        tmp_path / "recon-aabb1122.h5",
        tracer_name="FDG",
        scan_type="pet",
    )
    _create_h5_with_tracer(
        tmp_path / "recon-ccdd3344.h5",
        tracer_name=None,
        scan_type="ct",
    )
    return path


@pytest.fixture()
def minimal_manifest_path(tmp_path: Path) -> Path:
    """Manifest with no study/creators and minimal data."""
    toml_text = """\
_schema_version = 1
dataset_name = "test-minimal"

[[data]]
product = "sim"
id = "sha256:11223344"
file = "sim-11223344.h5"
timestamp = "2025-06-01T08:00:00Z"
"""
    path = tmp_path / "manifest.toml"
    path.write_text(toml_text)
    _create_h5_with_tracer(tmp_path / "sim-11223344.h5", tracer_name=None)
    return path


@pytest.fixture()
def no_data_manifest_path(tmp_path: Path) -> Path:
    """Manifest with no [[data]] entries."""
    toml_text = """\
_schema_version = 1
dataset_name = "empty-dataset"
"""
    path = tmp_path / "manifest.toml"
    path.write_text(toml_text)
    return path


def _create_h5_with_tracer(
    path: Path,
    tracer_name: str | None = None,
    scan_type: str | None = None,
) -> None:
    with h5py.File(path, "w") as f:
        if scan_type:
            f.attrs["scan_type"] = scan_type
        if tracer_name:
            meta = f.create_group("metadata")
            pet = meta.create_group("pet")
            tracer = pet.create_group("tracer")
            tracer.attrs["name"] = tracer_name


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_returns_dict(self, manifest_path: Path):
        result = generate(manifest_path)
        assert isinstance(result, dict)

    def test_title_contains_dataset_name(self, manifest_path: Path):
        result = generate(manifest_path)
        assert "dd01" in result["title"].lower()

    def test_creators_from_study(self, manifest_path: Path):
        result = generate(manifest_path)
        assert len(result["creators"]) == 2
        names = {c["name"] for c in result["creators"]}
        assert names == {"Jane Doe", "John Smith"}

    def test_creator_has_affiliation(self, manifest_path: Path):
        result = generate(manifest_path)
        jane = next(c for c in result["creators"] if c["name"] == "Jane Doe")
        assert jane["affiliation"] == "ETH Zurich"

    def test_dates_collected(self, manifest_path: Path):
        result = generate(manifest_path)
        assert len(result["dates"]) >= 1
        collected = [d for d in result["dates"] if d["dateType"] == "Collected"]
        assert len(collected) == 1
        assert collected[0]["date"] == "2024-07-24"

    def test_resource_type(self, manifest_path: Path):
        result = generate(manifest_path)
        assert result["resourceType"] == "Dataset"

    def test_subjects_from_scan_type(self, manifest_path: Path):
        result = generate(manifest_path)
        scan_subjects = [
            s for s in result["subjects"] if s.get("subjectScheme") == "DICOM Modality"
        ]
        subject_values = {s["subject"] for s in scan_subjects}
        assert "pet" in subject_values or "PET" in subject_values
        assert "ct" in subject_values or "CT" in subject_values

    def test_subjects_from_tracer(self, manifest_path: Path):
        result = generate(manifest_path)
        tracer_subjects = [
            s for s in result["subjects"] if s.get("subjectScheme") == "Radiotracer"
        ]
        assert len(tracer_subjects) == 1
        assert tracer_subjects[0]["subject"] == "FDG"

    def test_subjects_deduplicated(self, manifest_path: Path):
        result = generate(manifest_path)
        subject_tuples = [
            (s["subject"], s.get("subjectScheme")) for s in result["subjects"]
        ]
        assert len(subject_tuples) == len(set(subject_tuples))


class TestGenerateMinimal:
    def test_title_from_dataset_name(self, minimal_manifest_path: Path):
        result = generate(minimal_manifest_path)
        assert "test-minimal" in result["title"].lower()

    def test_no_creators_when_absent(self, minimal_manifest_path: Path):
        result = generate(minimal_manifest_path)
        assert result["creators"] == []

    def test_dates_collected(self, minimal_manifest_path: Path):
        result = generate(minimal_manifest_path)
        assert result["dates"][0]["date"] == "2025-06-01"

    def test_resource_type(self, minimal_manifest_path: Path):
        result = generate(minimal_manifest_path)
        assert result["resourceType"] == "Dataset"

    def test_no_subjects_when_no_scan_type(self, minimal_manifest_path: Path):
        result = generate(minimal_manifest_path)
        assert result["subjects"] == []


class TestGenerateNoData:
    def test_empty_dates(self, no_data_manifest_path: Path):
        result = generate(no_data_manifest_path)
        assert result["dates"] == []

    def test_empty_subjects(self, no_data_manifest_path: Path):
        result = generate(no_data_manifest_path)
        assert result["subjects"] == []


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------


class TestWrite:
    def test_creates_file(self, manifest_path: Path, tmp_path: Path):
        out = tmp_path / "output" / "datacite.yml"
        write(manifest_path, out)
        assert out.exists()

    def test_output_is_valid_yaml(self, manifest_path: Path, tmp_path: Path):
        out = tmp_path / "output" / "datacite.yml"
        write(manifest_path, out)
        parsed = yaml.safe_load(out.read_text())
        assert isinstance(parsed, dict)

    def test_yaml_has_title(self, manifest_path: Path, tmp_path: Path):
        out = tmp_path / "output" / "datacite.yml"
        write(manifest_path, out)
        parsed = yaml.safe_load(out.read_text())
        assert "title" in parsed

    def test_yaml_has_creators(self, manifest_path: Path, tmp_path: Path):
        out = tmp_path / "output" / "datacite.yml"
        write(manifest_path, out)
        parsed = yaml.safe_load(out.read_text())
        assert "creators" in parsed

    def test_yaml_round_trip_matches_generate(
        self, manifest_path: Path, tmp_path: Path
    ):
        out = tmp_path / "output" / "datacite.yml"
        write(manifest_path, out)
        parsed = yaml.safe_load(out.read_text())
        expected = generate(manifest_path)
        assert parsed == expected

    def test_idempotent(self, manifest_path: Path, tmp_path: Path):
        out = tmp_path / "output" / "datacite.yml"
        write(manifest_path, out)
        content1 = out.read_text()
        write(manifest_path, out)
        content2 = out.read_text()
        assert content1 == content2


# ---------------------------------------------------------------------------
# CLI integration (fd5 datacite)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Edge cases for _build_dates and _collect_tracer_subjects
# ---------------------------------------------------------------------------


class TestBuildDatesNoTimestamps:
    def test_data_entries_without_timestamp_produce_empty_dates(self, tmp_path: Path):
        """Covers datacite.py:84 — timestamps list empty returns []."""
        toml_text = """\
_schema_version = 1
dataset_name = "no-ts"

[[data]]
product = "recon"
id = "sha256:0000"
file = "recon-0000.h5"
"""
        path = tmp_path / "manifest.toml"
        path.write_text(toml_text)
        _create_h5_with_tracer(tmp_path / "recon-0000.h5")
        result = generate(path)
        assert result["dates"] == []


class TestCollectTracerSubjectsBytesName:
    def test_tracer_name_stored_as_bytes(self, tmp_path: Path):
        """Covers datacite.py:123,125 — bytes tracer name decoded."""
        import numpy as np

        toml_text = """\
_schema_version = 1
dataset_name = "bytes-tracer"

[[data]]
product = "recon"
id = "sha256:1111"
file = "recon-bytes.h5"
scan_type = "pet"
scan_type_vocabulary = "DICOM Modality"
timestamp = "2025-01-01T00:00:00Z"
"""
        path = tmp_path / "manifest.toml"
        path.write_text(toml_text)
        h5_path = tmp_path / "recon-bytes.h5"
        with h5py.File(h5_path, "w") as f:
            meta = f.create_group("metadata")
            pet = meta.create_group("pet")
            tracer = pet.create_group("tracer")
            tracer.attrs.create("name", data=np.bytes_(b"FDG"))
        result = generate(path)
        tracer_subjects = [
            s for s in result["subjects"] if s.get("subjectScheme") == "Radiotracer"
        ]
        assert len(tracer_subjects) == 1
        assert tracer_subjects[0]["subject"] == "FDG"


class TestCollectTracerSubjectsNoName:
    def test_tracer_group_without_name_attr(self, tmp_path: Path):
        """Covers datacite.py:123 — tracer group exists but name attr is missing."""
        toml_text = """\
_schema_version = 1
dataset_name = "no-name"

[[data]]
product = "recon"
id = "sha256:2222"
file = "recon-noname.h5"
scan_type = "pet"
scan_type_vocabulary = "DICOM Modality"
timestamp = "2025-01-01T00:00:00Z"
"""
        path = tmp_path / "manifest.toml"
        path.write_text(toml_text)
        h5_path = tmp_path / "recon-noname.h5"
        with h5py.File(h5_path, "w") as f:
            meta = f.create_group("metadata")
            pet = meta.create_group("pet")
            pet.create_group("tracer")
        result = generate(path)
        tracer_subjects = [
            s for s in result["subjects"] if s.get("subjectScheme") == "Radiotracer"
        ]
        assert len(tracer_subjects) == 0


class TestCollectTracerSubjectsException:
    def test_corrupt_h5_returns_no_subjects(self, tmp_path: Path):
        """Covers datacite.py:130-131 — exception in _collect_tracer_subjects."""
        toml_text = """\
_schema_version = 1
dataset_name = "corrupt"

[[data]]
product = "recon"
id = "sha256:bad"
file = "corrupt.h5"
scan_type = "pet"
scan_type_vocabulary = "DICOM Modality"
timestamp = "2025-01-01T00:00:00Z"
"""
        path = tmp_path / "manifest.toml"
        path.write_text(toml_text)
        (tmp_path / "corrupt.h5").write_bytes(b"not a valid hdf5 file")
        result = generate(path)
        tracer_subjects = [
            s for s in result["subjects"] if s.get("subjectScheme") == "Radiotracer"
        ]
        assert len(tracer_subjects) == 0


class TestDataciteCLI:
    def test_exits_zero(self, manifest_path: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["datacite", str(manifest_path.parent)])
        assert result.exit_code == 0, result.output

    def test_creates_datacite_yml(self, manifest_path: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        runner = CliRunner()
        runner.invoke(cli, ["datacite", str(manifest_path.parent)])
        assert (manifest_path.parent / "datacite.yml").exists()

    def test_custom_output(self, manifest_path: Path, tmp_path: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        out = tmp_path / "custom" / "datacite.yml"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["datacite", str(manifest_path.parent), "--output", str(out)]
        )
        assert result.exit_code == 0
        assert out.exists()

    def test_nonexistent_dir_exits_nonzero(self, tmp_path: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["datacite", str(tmp_path / "nope")])
        assert result.exit_code != 0

    def test_missing_manifest_exits_nonzero(self, tmp_path: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["datacite", str(tmp_path)])
        assert result.exit_code != 0
