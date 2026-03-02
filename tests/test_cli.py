"""Tests for fd5.cli — validate, info, schema-dump, manifest commands."""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest
from click.testing import CliRunner

from fd5.cli import cli
from fd5.hash import compute_content_hash
from fd5.h5io import dict_to_h5
from fd5.schema import embed_schema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def valid_h5(tmp_path: Path) -> Path:
    """Create a valid fd5 file with embedded schema and correct content_hash."""
    path = tmp_path / "valid.h5"
    schema_dict = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "_schema_version": {"type": "integer"},
            "product": {"type": "string"},
        },
        "required": ["_schema_version", "product"],
    }
    with h5py.File(path, "w") as f:
        embed_schema(f, schema_dict)
        f.attrs["product"] = "test/recon"
        f.attrs["id"] = "sha256:abc123"
        f.attrs["timestamp"] = "2026-01-15T10:00:00Z"
        f.create_dataset("volume", data=np.zeros((4, 4), dtype=np.float32))
        f.attrs["content_hash"] = compute_content_hash(f)
    return path


@pytest.fixture()
def invalid_schema_h5(tmp_path: Path) -> Path:
    """Create an fd5 file that fails schema validation (missing required attr)."""
    path = tmp_path / "invalid_schema.h5"
    schema_dict = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "product": {"type": "string"},
        },
        "required": ["product"],
    }
    with h5py.File(path, "w") as f:
        embed_schema(f, schema_dict)
        # 'product' missing — validation should fail
        f.attrs["content_hash"] = compute_content_hash(f)
    return path


@pytest.fixture()
def bad_hash_h5(tmp_path: Path) -> Path:
    """Create an fd5 file with valid schema but wrong content_hash."""
    path = tmp_path / "bad_hash.h5"
    schema_dict = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "product": {"type": "string"},
        },
        "required": ["product"],
    }
    with h5py.File(path, "w") as f:
        embed_schema(f, schema_dict)
        f.attrs["product"] = "test/recon"
        f.attrs["content_hash"] = (
            "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        )
    return path


@pytest.fixture()
def no_schema_h5(tmp_path: Path) -> Path:
    """Create an HDF5 file without an embedded schema."""
    path = tmp_path / "no_schema.h5"
    with h5py.File(path, "w") as f:
        f.attrs["product"] = "test/recon"
    return path


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Create a directory with sample .h5 files for manifest generation."""
    _create_h5(
        tmp_path / "recon-aabb.h5",
        root_attrs={
            "_schema_version": 1,
            "product": "recon",
            "id": "sha256:aabb",
            "id_inputs": "timestamp + scanner_uuid",
            "name": "PET recon",
            "description": "PET reconstruction",
            "content_hash": "sha256:deadbeef",
            "timestamp": "2026-01-15T10:00:00Z",
        },
    )
    _create_h5(
        tmp_path / "roi-ccdd.h5",
        root_attrs={
            "_schema_version": 1,
            "product": "roi",
            "id": "sha256:ccdd",
            "id_inputs": "reference + method",
            "name": "Tumor ROI",
            "description": "Manual contours",
            "content_hash": "sha256:cafebabe",
            "timestamp": "2026-01-16T11:00:00Z",
        },
    )
    return tmp_path


def _create_h5(path: Path, root_attrs: dict) -> None:
    with h5py.File(path, "w") as f:
        dict_to_h5(f, root_attrs)


# ---------------------------------------------------------------------------
# fd5 validate
# ---------------------------------------------------------------------------


class TestValidateCommand:
    def test_valid_file_exits_zero(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["validate", str(valid_h5)])
        assert result.exit_code == 0

    def test_valid_file_shows_ok(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["validate", str(valid_h5)])
        assert "ok" in result.output.lower() or "valid" in result.output.lower()

    def test_schema_errors_exit_one(self, runner: CliRunner, invalid_schema_h5: Path):
        result = runner.invoke(cli, ["validate", str(invalid_schema_h5)])
        assert result.exit_code == 1

    def test_schema_errors_show_details(
        self, runner: CliRunner, invalid_schema_h5: Path
    ):
        result = runner.invoke(cli, ["validate", str(invalid_schema_h5)])
        assert "product" in result.output.lower()

    def test_bad_hash_exits_one(self, runner: CliRunner, bad_hash_h5: Path):
        result = runner.invoke(cli, ["validate", str(bad_hash_h5)])
        assert result.exit_code == 1

    def test_bad_hash_mentions_hash(self, runner: CliRunner, bad_hash_h5: Path):
        result = runner.invoke(cli, ["validate", str(bad_hash_h5)])
        assert (
            "content_hash" in result.output.lower() or "hash" in result.output.lower()
        )

    def test_no_schema_exits_one(self, runner: CliRunner, no_schema_h5: Path):
        result = runner.invoke(cli, ["validate", str(no_schema_h5)])
        assert result.exit_code == 1

    def test_nonexistent_file_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["validate", str(tmp_path / "ghost.h5")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fd5 info
# ---------------------------------------------------------------------------


class TestInfoCommand:
    def test_exits_zero(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["info", str(valid_h5)])
        assert result.exit_code == 0

    def test_shows_product(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["info", str(valid_h5)])
        assert "test/recon" in result.output

    def test_shows_id(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["info", str(valid_h5)])
        assert "sha256:abc123" in result.output

    def test_shows_timestamp(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["info", str(valid_h5)])
        assert "2026-01-15" in result.output

    def test_shows_content_hash(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["info", str(valid_h5)])
        assert "content_hash" in result.output.lower() or "sha256:" in result.output

    def test_shows_dataset_shapes(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["info", str(valid_h5)])
        assert (
            "(4, 4)" in result.output
            or "4 x 4" in result.output
            or "4, 4" in result.output
        )

    def test_nonexistent_file_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["info", str(tmp_path / "ghost.h5")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fd5 schema-dump
# ---------------------------------------------------------------------------


class TestSchemaDumpCommand:
    def test_exits_zero(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["schema-dump", str(valid_h5)])
        assert result.exit_code == 0

    def test_outputs_valid_json(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["schema-dump", str(valid_h5)])
        parsed = json.loads(result.output)
        assert isinstance(parsed, dict)

    def test_schema_has_expected_fields(self, runner: CliRunner, valid_h5: Path):
        result = runner.invoke(cli, ["schema-dump", str(valid_h5)])
        parsed = json.loads(result.output)
        assert "$schema" in parsed
        assert parsed["type"] == "object"

    def test_no_schema_exits_one(self, runner: CliRunner, no_schema_h5: Path):
        result = runner.invoke(cli, ["schema-dump", str(no_schema_h5)])
        assert result.exit_code == 1

    def test_nonexistent_file_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["schema-dump", str(tmp_path / "ghost.h5")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fd5 manifest
# ---------------------------------------------------------------------------


class TestManifestCommand:
    def test_exits_zero(self, runner: CliRunner, data_dir: Path):
        result = runner.invoke(cli, ["manifest", str(data_dir)])
        assert result.exit_code == 0

    def test_creates_manifest_file(self, runner: CliRunner, data_dir: Path):
        runner.invoke(cli, ["manifest", str(data_dir)])
        assert (data_dir / "manifest.toml").exists()

    def test_manifest_is_valid_toml(self, runner: CliRunner, data_dir: Path):
        import tomllib

        runner.invoke(cli, ["manifest", str(data_dir)])
        content = (data_dir / "manifest.toml").read_text()
        parsed = tomllib.loads(content)
        assert isinstance(parsed, dict)

    def test_manifest_has_data_entries(self, runner: CliRunner, data_dir: Path):
        import tomllib

        runner.invoke(cli, ["manifest", str(data_dir)])
        parsed = tomllib.loads((data_dir / "manifest.toml").read_text())
        assert len(parsed["data"]) == 2

    def test_custom_output_path(
        self, runner: CliRunner, data_dir: Path, tmp_path: Path
    ):
        out = tmp_path / "custom" / "out.toml"
        result = runner.invoke(cli, ["manifest", str(data_dir), "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_nonexistent_dir_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["manifest", str(tmp_path / "nope")])
        assert result.exit_code != 0

    def test_empty_dir(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["manifest", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "manifest.toml").exists()


# ---------------------------------------------------------------------------
# fd5 --help
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# fd5 rocrate
# ---------------------------------------------------------------------------


class TestRocrateCommand:
    def test_exits_zero(self, runner: CliRunner, data_dir: Path):
        result = runner.invoke(cli, ["rocrate", str(data_dir)])
        assert result.exit_code == 0

    def test_creates_default_output(self, runner: CliRunner, data_dir: Path):
        runner.invoke(cli, ["rocrate", str(data_dir)])
        assert (data_dir / "ro-crate-metadata.json").exists()

    def test_custom_output_path(
        self, runner: CliRunner, data_dir: Path, tmp_path: Path
    ):
        out = tmp_path / "custom" / "crate.json"
        result = runner.invoke(cli, ["rocrate", str(data_dir), "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_nonexistent_dir_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["rocrate", str(tmp_path / "nope")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# _format_attr (bytes branch)
# ---------------------------------------------------------------------------


class TestFormatAttr:
    def test_bytes_attr_decoded(self, runner: CliRunner, tmp_path: Path):
        """Covers cli.py:156 — _format_attr decoding bytes to str."""
        path = tmp_path / "bytes_attr.h5"
        with h5py.File(path, "w") as f:
            f.attrs["name"] = np.bytes_(b"hello-bytes")
        result = runner.invoke(cli, ["info", str(path)])
        assert result.exit_code == 0
        assert "hello-bytes" in result.output


# ---------------------------------------------------------------------------
# fd5 migrate
# ---------------------------------------------------------------------------


def _make_v1_h5(path: Path) -> Path:
    """Create a minimal sealed v1 fd5 file for CLI migration tests."""
    schema_dict = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "_schema_version": {"type": "integer"},
            "product": {"type": "string"},
        },
        "required": ["_schema_version", "product"],
    }
    with h5py.File(path, "w") as f:
        f.attrs["product"] = "test/climock"
        f.attrs["name"] = "sample"
        f.attrs["description"] = "A v1 file"
        f.attrs["timestamp"] = "2026-01-15T10:00:00Z"
        f.attrs["id"] = "sha256:abc123"
        f.attrs["id_inputs"] = "product + name + timestamp"
        f.attrs["_schema_version"] = np.int64(1)
        embed_schema(f, schema_dict)
        f.create_dataset("volume", data=np.zeros((4, 4), dtype=np.float32))
        f.attrs["content_hash"] = compute_content_hash(f)
    return path


def _cli_v1_to_v2(src: h5py.File, dst: h5py.File) -> None:
    if "volume" in src:
        dst.create_dataset("volume", data=src["volume"][...])
    dst.attrs["cli_added"] = "yes"


class TestMigrateCommand:
    @pytest.fixture(autouse=True)
    def _register(self):
        from fd5.migrate import clear_migrations, register_migration

        register_migration("test/climock", 1, 2, _cli_v1_to_v2)
        yield
        clear_migrations()

    def test_exits_zero(self, runner: CliRunner, tmp_path: Path):
        src = _make_v1_h5(tmp_path / "src.h5")
        out = tmp_path / "out.h5"
        result = runner.invoke(cli, ["migrate", str(src), str(out), "--target", "2"])
        assert result.exit_code == 0, result.output

    def test_creates_output_file(self, runner: CliRunner, tmp_path: Path):
        src = _make_v1_h5(tmp_path / "src.h5")
        out = tmp_path / "out.h5"
        runner.invoke(cli, ["migrate", str(src), str(out), "--target", "2"])
        assert out.exists()

    def test_prints_confirmation(self, runner: CliRunner, tmp_path: Path):
        src = _make_v1_h5(tmp_path / "src.h5")
        out = tmp_path / "out.h5"
        result = runner.invoke(cli, ["migrate", str(src), str(out), "--target", "2"])
        assert "migrated" in result.output.lower() or "out.h5" in result.output

    def test_nonexistent_source_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            cli,
            [
                "migrate",
                str(tmp_path / "ghost.h5"),
                str(tmp_path / "o.h5"),
                "--target",
                "2",
            ],
        )
        assert result.exit_code != 0

    def test_same_version_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        src = _make_v1_h5(tmp_path / "src.h5")
        out = tmp_path / "out.h5"
        result = runner.invoke(cli, ["migrate", str(src), str(out), "--target", "1"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fd5 --help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_exits_zero(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_help_lists_commands(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        for cmd in ("validate", "info", "schema-dump", "manifest", "migrate"):
            assert cmd in result.output


# ---------------------------------------------------------------------------
# Helpers for edit/log tests
# ---------------------------------------------------------------------------


def _make_sealed_h5(path: Path) -> Path:
    """Create a minimal sealed fd5 file with a group attribute to edit."""
    schema_dict = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "_schema_version": {"type": "integer"},
            "product": {"type": "string"},
        },
        "required": ["_schema_version", "product"],
    }
    with h5py.File(path, "w") as f:
        embed_schema(f, schema_dict)
        f.attrs["product"] = "test/recon"
        f.attrs["name"] = "original_name"
        f.attrs["id"] = "sha256:abc123"
        f.attrs["timestamp"] = "2026-01-15T10:00:00Z"
        g = f.create_group("calibration")
        g.attrs["factor"] = "1.0"
        g.attrs["description"] = "Calibration parameters"
        f.create_dataset("volume", data=np.zeros((4, 4), dtype=np.float32))
        f.attrs["content_hash"] = compute_content_hash(f)
    return path


# ---------------------------------------------------------------------------
# fd5 edit
# ---------------------------------------------------------------------------


class TestEditCommand:
    def test_edit_in_place(self, runner: CliRunner, tmp_path: Path):
        """fd5 edit --in-place modifies the file directly and reseals."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        result = runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/calibration.factor",
                "1.05",
                "-m",
                "Updated cal factor",
                "--in-place",
            ],
        )
        assert result.exit_code == 0, result.output
        # Verify the attribute was changed
        with h5py.File(src, "r") as f:
            assert f["calibration"].attrs["factor"] == "1.05"

    def test_edit_creates_audit_entry(self, runner: CliRunner, tmp_path: Path):
        """fd5 edit should create an audit log entry."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/calibration.factor",
                "1.05",
                "-m",
                "Updated cal factor",
                "--in-place",
            ],
        )
        with h5py.File(src, "r") as f:
            assert "_fd5_audit_log" in f.attrs
            raw = f.attrs["_fd5_audit_log"]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            log = json.loads(raw)
            assert len(log) == 1
            assert log[0]["message"] == "Updated cal factor"
            assert log[0]["changes"][0]["old"] == "1.0"
            assert log[0]["changes"][0]["new"] == "1.05"

    def test_edit_preserves_existing_log(self, runner: CliRunner, tmp_path: Path):
        """A second edit should append to the existing audit log, not overwrite."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/calibration.factor",
                "1.05",
                "-m",
                "First edit",
                "--in-place",
            ],
        )
        runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/calibration.factor",
                "1.10",
                "-m",
                "Second edit",
                "--in-place",
            ],
        )
        with h5py.File(src, "r") as f:
            raw = f.attrs["_fd5_audit_log"]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            log = json.loads(raw)
            assert len(log) == 2
            assert log[0]["message"] == "First edit"
            assert log[1]["message"] == "Second edit"

    def test_edit_copy_on_write(self, runner: CliRunner, tmp_path: Path):
        """Without --in-place, edit creates a new file."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        out = tmp_path / "edited.h5"
        result = runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/calibration.factor",
                "1.05",
                "-m",
                "Copy edit",
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        # Source should be unchanged
        with h5py.File(src, "r") as f:
            assert f["calibration"].attrs["factor"] == "1.0"
        # Output should have the new value
        with h5py.File(out, "r") as f:
            assert f["calibration"].attrs["factor"] == "1.05"

    def test_edit_reseals_content_hash(self, runner: CliRunner, tmp_path: Path):
        """After edit, the content_hash should be recomputed and valid."""
        from fd5.hash import verify

        src = _make_sealed_h5(tmp_path / "src.h5")
        runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/calibration.factor",
                "1.05",
                "-m",
                "Reseal test",
                "--in-place",
            ],
        )
        assert verify(src) is True

    def test_edit_records_parent_hash(self, runner: CliRunner, tmp_path: Path):
        """The audit entry should record the content_hash BEFORE the edit."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        with h5py.File(src, "r") as f:
            original_hash = f.attrs["content_hash"]
            if isinstance(original_hash, bytes):
                original_hash = original_hash.decode("utf-8")

        runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/calibration.factor",
                "1.05",
                "-m",
                "Parent hash test",
                "--in-place",
            ],
        )
        with h5py.File(src, "r") as f:
            raw = f.attrs["_fd5_audit_log"]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            log = json.loads(raw)
            assert log[0]["parent_hash"] == original_hash

    def test_edit_root_attr(self, runner: CliRunner, tmp_path: Path):
        """Editing a root-level attribute works with '/' path."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        result = runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/.name",
                "new_name",
                "-m",
                "Rename",
                "--in-place",
            ],
        )
        assert result.exit_code == 0, result.output
        with h5py.File(src, "r") as f:
            assert f.attrs["name"] == "new_name"

    def test_edit_nonexistent_file_exits_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ):
        result = runner.invoke(
            cli,
            [
                "edit",
                str(tmp_path / "ghost.h5"),
                "/.name",
                "val",
                "-m",
                "msg",
                "--in-place",
            ],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fd5 log
# ---------------------------------------------------------------------------


class TestLogCommand:
    def test_log_empty(self, runner: CliRunner, tmp_path: Path):
        """fd5 log on a file with no audit log prints informative message."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        result = runner.invoke(cli, ["log", str(src)])
        assert result.exit_code == 0
        assert "no audit" in result.output.lower() or "empty" in result.output.lower()

    def test_log_output_format(self, runner: CliRunner, tmp_path: Path):
        """fd5 log shows human-readable entries after an edit."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/calibration.factor",
                "1.05",
                "-m",
                "Updated cal factor",
                "--in-place",
            ],
        )
        result = runner.invoke(cli, ["log", str(src)])
        assert result.exit_code == 0
        assert "Updated cal factor" in result.output

    def test_log_json_flag(self, runner: CliRunner, tmp_path: Path):
        """fd5 log --json outputs valid JSON."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/calibration.factor",
                "1.05",
                "-m",
                "JSON test",
                "--in-place",
            ],
        )
        result = runner.invoke(cli, ["log", str(src), "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["message"] == "JSON test"

    def test_log_nonexistent_file_exits_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ):
        result = runner.invoke(cli, ["log", str(tmp_path / "ghost.h5")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fd5 validate with chain verification
# ---------------------------------------------------------------------------


class TestValidateChainIntegration:
    def test_validate_shows_chain_status(self, runner: CliRunner, tmp_path: Path):
        """fd5 validate on a file with valid audit chain should report chain OK."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        # Make an edit to create an audit log
        runner.invoke(
            cli,
            [
                "edit",
                str(src),
                "/calibration.factor",
                "1.05",
                "-m",
                "Chain test",
                "--in-place",
            ],
        )
        result = runner.invoke(cli, ["validate", str(src)])
        assert result.exit_code == 0
        assert "chain" in result.output.lower() or "audit" in result.output.lower()

    def test_validate_broken_chain_exits_one(self, runner: CliRunner, tmp_path: Path):
        """fd5 validate on a file with broken audit chain should exit 1."""
        src = _make_sealed_h5(tmp_path / "src.h5")
        # Manually inject a broken audit log
        with h5py.File(src, "a") as f:
            log = [
                {
                    "parent_hash": "sha256:totally_wrong_hash",
                    "timestamp": "2026-03-02T14:30:00Z",
                    "author": {"type": "anonymous", "id": "", "name": "Anonymous"},
                    "message": "broken",
                    "changes": [],
                }
            ]
            f.attrs["_fd5_audit_log"] = json.dumps(log)
            f.attrs["content_hash"] = compute_content_hash(f)
        result = runner.invoke(cli, ["validate", str(src)])
        assert result.exit_code == 1
        assert "chain" in result.output.lower() or "audit" in result.output.lower()
