"""Tests for fd5.manifest — build_manifest, write_manifest, read_manifest."""

from __future__ import annotations

import tomllib
from pathlib import Path

import h5py
import pytest

from fd5.h5io import dict_to_h5
from fd5.manifest import build_manifest, read_manifest, write_manifest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with sample .h5 files."""
    _create_h5(
        tmp_path / "recon-aabb1122.h5",
        root_attrs={
            "_schema_version": 1,
            "product": "recon",
            "id": "sha256:aabb112233445566",
            "id_inputs": "timestamp + scanner_uuid",
            "name": "PET recon",
            "description": "Whole-body PET reconstruction",
            "content_hash": "sha256:deadbeef",
            "timestamp": "2024-07-24T19:06:10+02:00",
            "scan_type": "pet",
            "duration_s": 367.0,
        },
        groups={
            "study": {"type": "clinical"},
            "subject": {"species": "human", "birth_date": "1959-03-15"},
        },
    )
    _create_h5(
        tmp_path / "roi-ccdd3344.h5",
        root_attrs={
            "_schema_version": 1,
            "product": "roi",
            "id": "sha256:ccdd334455667788",
            "id_inputs": "reference_image_id + method_type",
            "name": "Tumor ROI",
            "description": "Manual tumor contours",
            "content_hash": "sha256:cafebabe",
            "timestamp": "2026-01-15T10:30:00+01:00",
            "method": "manual",
            "n_regions": 3,
        },
        groups={
            "study": {"type": "clinical"},
            "subject": {"species": "human", "birth_date": "1959-03-15"},
        },
    )
    return tmp_path


def _create_h5(
    path: Path,
    root_attrs: dict,
    groups: dict | None = None,
) -> None:
    with h5py.File(path, "w") as f:
        dict_to_h5(f, root_attrs)
        if groups:
            for name, attrs in groups.items():
                g = f.create_group(name)
                dict_to_h5(g, attrs)


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------


class TestBuildManifest:
    def test_returns_dict(self, data_dir: Path):
        result = build_manifest(data_dir)
        assert isinstance(result, dict)

    def test_schema_version(self, data_dir: Path):
        result = build_manifest(data_dir)
        assert result["_schema_version"] == 1

    def test_dataset_name_from_directory(self, data_dir: Path):
        result = build_manifest(data_dir)
        assert result["dataset_name"] == data_dir.name

    def test_study_extracted(self, data_dir: Path):
        result = build_manifest(data_dir)
        assert result["study"] == {"type": "clinical"}

    def test_subject_extracted(self, data_dir: Path):
        result = build_manifest(data_dir)
        assert result["subject"] == {"species": "human", "birth_date": "1959-03-15"}

    def test_data_entries_count(self, data_dir: Path):
        result = build_manifest(data_dir)
        assert len(result["data"]) == 2

    def test_data_entry_has_required_fields(self, data_dir: Path):
        result = build_manifest(data_dir)
        for entry in result["data"]:
            assert "product" in entry
            assert "id" in entry
            assert "file" in entry

    def test_data_entry_product(self, data_dir: Path):
        result = build_manifest(data_dir)
        products = {e["product"] for e in result["data"]}
        assert products == {"recon", "roi"}

    def test_data_entry_file_is_filename(self, data_dir: Path):
        result = build_manifest(data_dir)
        for entry in result["data"]:
            assert entry["file"].endswith(".h5")
            assert "/" not in entry["file"]

    def test_data_entry_includes_timestamp(self, data_dir: Path):
        result = build_manifest(data_dir)
        for entry in result["data"]:
            assert "timestamp" in entry

    def test_data_entry_includes_product_specific_fields(self, data_dir: Path):
        result = build_manifest(data_dir)
        recon = next(e for e in result["data"] if e["product"] == "recon")
        assert recon["scan_type"] == "pet"
        assert recon["duration_s"] == 367.0

        roi = next(e for e in result["data"] if e["product"] == "roi")
        assert roi["method"] == "manual"
        assert roi["n_regions"] == 3

    def test_data_entry_excludes_internal_attrs(self, data_dir: Path):
        result = build_manifest(data_dir)
        for entry in result["data"]:
            assert "_schema_version" not in entry
            assert "content_hash" not in entry
            assert "id_inputs" not in entry
            assert "_schema" not in entry
            assert "name" not in entry
            assert "description" not in entry

    def test_empty_directory(self, tmp_path: Path):
        result = build_manifest(tmp_path)
        assert result["data"] == []
        assert result["_schema_version"] == 1
        assert result["dataset_name"] == tmp_path.name

    def test_files_sorted_by_name(self, data_dir: Path):
        result = build_manifest(data_dir)
        files = [e["file"] for e in result["data"]]
        assert files == sorted(files)

    def test_no_study_or_subject_when_absent(self, tmp_path: Path):
        _create_h5(
            tmp_path / "sim-11223344.h5",
            root_attrs={
                "_schema_version": 1,
                "product": "sim",
                "id": "sha256:1122334455667788",
                "id_inputs": "config_hash + seed",
                "name": "Sim run",
                "description": "Monte Carlo simulation",
                "content_hash": "sha256:00000000",
            },
            groups=None,
        )
        result = build_manifest(tmp_path)
        assert "study" not in result
        assert "subject" not in result


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------


class TestWriteManifest:
    def test_creates_file(self, data_dir: Path, tmp_path: Path):
        out = tmp_path / "output" / "manifest.toml"
        write_manifest(data_dir, out)
        assert out.exists()

    def test_output_is_valid_toml(self, data_dir: Path, tmp_path: Path):
        out = tmp_path / "output" / "manifest.toml"
        write_manifest(data_dir, out)
        parsed = tomllib.loads(out.read_text())
        assert isinstance(parsed, dict)

    def test_schema_version_in_output(self, data_dir: Path, tmp_path: Path):
        out = tmp_path / "output" / "manifest.toml"
        write_manifest(data_dir, out)
        parsed = tomllib.loads(out.read_text())
        assert parsed["_schema_version"] == 1

    def test_data_entries_in_output(self, data_dir: Path, tmp_path: Path):
        out = tmp_path / "output" / "manifest.toml"
        write_manifest(data_dir, out)
        parsed = tomllib.loads(out.read_text())
        assert len(parsed["data"]) == 2


# ---------------------------------------------------------------------------
# read_manifest
# ---------------------------------------------------------------------------


class TestReadManifest:
    def test_round_trip(self, data_dir: Path, tmp_path: Path):
        out = tmp_path / "output" / "manifest.toml"
        write_manifest(data_dir, out)
        result = read_manifest(out)
        assert result["_schema_version"] == 1
        assert len(result["data"]) == 2

    def test_reads_hand_crafted_toml(self, tmp_path: Path):
        toml_text = """\
_schema_version = 1
dataset_name = "test_dataset"

[study]
type = "clinical"

[[data]]
product = "recon"
id = "sha256:aabb1122"
file = "recon-aabb1122.h5"
timestamp = "2024-07-24T19:06:10+02:00"
"""
        toml_file = tmp_path / "manifest.toml"
        toml_file.write_text(toml_text)
        result = read_manifest(toml_file)
        assert result["dataset_name"] == "test_dataset"
        assert result["data"][0]["product"] == "recon"

    def test_returns_dict(self, tmp_path: Path):
        toml_file = tmp_path / "manifest.toml"
        toml_file.write_text('_schema_version = 1\ndataset_name = "x"\n')
        result = read_manifest(toml_file)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Lazy iteration
# ---------------------------------------------------------------------------


class TestLazyIteration:
    def test_glob_returns_generator(self, data_dir: Path):
        """Path.glob returns a generator, not a list — verifies lazy scanning."""
        glob_result = data_dir.glob("*.h5")
        assert hasattr(glob_result, "__next__")
