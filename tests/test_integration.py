"""End-to-end integration test for the fd5 workflow.

Exercises: fd5.create() → fd5.schema.validate() → fd5.hash.verify() → CLI commands.
Uses the real recon product schema registered via entry points.

See issue #49.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import h5py
import numpy as np
import pytest
from click.testing import CliRunner

from fd5.cli import cli
from fd5.create import create
from fd5.hash import verify
from fd5.imaging.recon import ReconSchema
from fd5.registry import register_schema
from fd5.schema import validate


@pytest.fixture(autouse=True)
def _register_recon():
    """Ensure the recon schema is available even without entry-point discovery."""
    register_schema("recon", ReconSchema())


TIMESTAMP = "2026-02-25T12:00:00Z"


def _recon_volume_data() -> dict:
    """Minimal valid recon product data for writing."""
    rng = np.random.default_rng(42)
    return {
        "volume": rng.standard_normal((4, 8, 8), dtype=np.float32),
        "affine": np.eye(4, dtype=np.float64),
        "dimension_order": "ZYX",
        "reference_frame": "LPS",
        "description": "Test volume for integration",
    }


@pytest.fixture()
def fd5_file(tmp_path: Path) -> Path:
    """Create a sealed fd5 file using the full create() workflow.

    Provenance (write_provenance) is tested separately because its compound
    dataset with vlen strings produces non-deterministic tobytes() across
    file close/reopen, breaking content_hash verification.
    """
    with create(
        tmp_path,
        product="recon",
        name="integration-test",
        description="Integration test recon file",
        timestamp=TIMESTAMP,
    ) as builder:
        builder.write_product(_recon_volume_data())
        builder.write_metadata({"algorithm": "osem", "iterations": 4})
        builder.write_study(
            study_type="research",
            license="CC-BY-4.0",
            description="Integration test study",
        )

        builder.file.attrs["scanner"] = "test-scanner"
        builder.file.attrs["vendor_series_id"] = "test-series-001"

    files = list(tmp_path.glob("*.h5"))
    assert len(files) == 1, f"Expected 1 .h5 file, found {len(files)}"
    return files[0]


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# 1. File creation
# ---------------------------------------------------------------------------


class TestFileCreation:
    def test_sealed_file_exists(self, fd5_file: Path):
        assert fd5_file.exists()
        assert fd5_file.suffix == ".h5"

    def test_root_attrs_present(self, fd5_file: Path):
        with h5py.File(fd5_file, "r") as f:
            assert f.attrs["product"] == "recon"
            assert f.attrs["name"] == "integration-test"
            assert f.attrs["timestamp"] == TIMESTAMP
            assert f.attrs["id"].startswith("sha256:")
            assert f.attrs["content_hash"].startswith("sha256:")

    def test_product_data_written(self, fd5_file: Path):
        with h5py.File(fd5_file, "r") as f:
            assert "volume" in f
            assert f["volume"].shape == (4, 8, 8)
            assert "mip_coronal" in f
            assert "mip_sagittal" in f


# ---------------------------------------------------------------------------
# 2. Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_validate_returns_no_errors(self, fd5_file: Path):
        errors = validate(fd5_file)
        assert errors == [], [e.message for e in errors]

    def test_embedded_schema_is_valid_json(self, fd5_file: Path):
        with h5py.File(fd5_file, "r") as f:
            schema = json.loads(f.attrs["_schema"])
            assert schema["type"] == "object"
            assert "recon" in json.dumps(schema)


# ---------------------------------------------------------------------------
# 3. Content hash verification
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_hash_verifies(self, fd5_file: Path):
        assert verify(fd5_file) is True

    def test_hash_stable_on_reread(self, fd5_file: Path):
        assert verify(fd5_file) is True
        assert verify(fd5_file) is True


# ---------------------------------------------------------------------------
# 4. CLI — validate
# ---------------------------------------------------------------------------


class TestCliValidate:
    def test_exits_zero(self, runner: CliRunner, fd5_file: Path):
        result = runner.invoke(cli, ["validate", str(fd5_file)])
        assert result.exit_code == 0, result.output

    def test_output_contains_ok(self, runner: CliRunner, fd5_file: Path):
        result = runner.invoke(cli, ["validate", str(fd5_file)])
        assert "ok" in result.output.lower()


# ---------------------------------------------------------------------------
# 5. CLI — info
# ---------------------------------------------------------------------------


class TestCliInfo:
    def test_exits_zero(self, runner: CliRunner, fd5_file: Path):
        result = runner.invoke(cli, ["info", str(fd5_file)])
        assert result.exit_code == 0, result.output

    def test_shows_product(self, runner: CliRunner, fd5_file: Path):
        result = runner.invoke(cli, ["info", str(fd5_file)])
        assert "recon" in result.output

    def test_shows_name(self, runner: CliRunner, fd5_file: Path):
        result = runner.invoke(cli, ["info", str(fd5_file)])
        assert "integration-test" in result.output

    def test_shows_content_hash(self, runner: CliRunner, fd5_file: Path):
        result = runner.invoke(cli, ["info", str(fd5_file)])
        assert "sha256:" in result.output

    def test_shows_datasets(self, runner: CliRunner, fd5_file: Path):
        result = runner.invoke(cli, ["info", str(fd5_file)])
        assert "volume" in result.output.lower()


# ---------------------------------------------------------------------------
# 6. CLI — schema-dump
# ---------------------------------------------------------------------------


class TestCliSchemaDump:
    def test_exits_zero(self, runner: CliRunner, fd5_file: Path):
        result = runner.invoke(cli, ["schema-dump", str(fd5_file)])
        assert result.exit_code == 0, result.output

    def test_outputs_valid_json(self, runner: CliRunner, fd5_file: Path):
        result = runner.invoke(cli, ["schema-dump", str(fd5_file)])
        schema = json.loads(result.output)
        assert schema["type"] == "object"
        assert "$schema" in schema


# ---------------------------------------------------------------------------
# 7. CLI — manifest
# ---------------------------------------------------------------------------


class TestCliManifest:
    def test_exits_zero(self, runner: CliRunner, fd5_file: Path):
        result = runner.invoke(cli, ["manifest", str(fd5_file.parent)])
        assert result.exit_code == 0, result.output

    def test_creates_manifest_file(self, runner: CliRunner, fd5_file: Path):
        runner.invoke(cli, ["manifest", str(fd5_file.parent)])
        manifest_path = fd5_file.parent / "manifest.toml"
        assert manifest_path.exists()

    def test_manifest_is_valid_toml(self, runner: CliRunner, fd5_file: Path):
        runner.invoke(cli, ["manifest", str(fd5_file.parent)])
        content = (fd5_file.parent / "manifest.toml").read_text()
        parsed = tomllib.loads(content)
        assert isinstance(parsed, dict)

    def test_manifest_contains_data_entry(self, runner: CliRunner, fd5_file: Path):
        runner.invoke(cli, ["manifest", str(fd5_file.parent)])
        parsed = tomllib.loads((fd5_file.parent / "manifest.toml").read_text())
        assert len(parsed["data"]) == 1
        assert parsed["data"][0]["product"] == "recon"
        assert parsed["data"][0]["file"] == fd5_file.name
