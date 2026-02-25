"""Tests for fd5.quality — description quality validation heuristics."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest
from click.testing import CliRunner

from fd5.cli import cli
from fd5.quality import Warning, check_descriptions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def clean_h5(tmp_path: Path) -> Path:
    """An fd5 file where every group and dataset has a good description."""
    path = tmp_path / "clean.h5"
    with h5py.File(path, "w") as f:
        f.attrs["description"] = "Root-level dataset of PET reconstruction images"
        g = f.create_group("metadata")
        g.attrs["description"] = "Reconstruction parameters and settings"
        ds = f.create_dataset("volume", data=np.zeros((4, 4), dtype=np.float32))
        ds.attrs["description"] = "Reconstructed image volume in Bq/mL"
    return path


@pytest.fixture()
def no_root_desc_h5(tmp_path: Path) -> Path:
    """An fd5 file missing the root description attribute."""
    path = tmp_path / "no_root.h5"
    with h5py.File(path, "w") as f:
        f.attrs["product"] = "recon"
        ds = f.create_dataset("volume", data=np.zeros((4,), dtype=np.float32))
        ds.attrs["description"] = "Reconstructed image volume in Bq/mL"
    return path


@pytest.fixture()
def empty_root_desc_h5(tmp_path: Path) -> Path:
    """An fd5 file with an empty root description attribute."""
    path = tmp_path / "empty_root.h5"
    with h5py.File(path, "w") as f:
        f.attrs["description"] = ""
        ds = f.create_dataset("volume", data=np.zeros((4,), dtype=np.float32))
        ds.attrs["description"] = "Reconstructed image volume in Bq/mL"
    return path


@pytest.fixture()
def missing_group_desc_h5(tmp_path: Path) -> Path:
    """An fd5 file with a group missing its description."""
    path = tmp_path / "missing_group.h5"
    with h5py.File(path, "w") as f:
        f.attrs["description"] = "Root-level dataset of PET reconstruction images"
        f.create_group("metadata")  # no description
    return path


@pytest.fixture()
def missing_dataset_desc_h5(tmp_path: Path) -> Path:
    """An fd5 file with a dataset missing its description."""
    path = tmp_path / "missing_ds.h5"
    with h5py.File(path, "w") as f:
        f.attrs["description"] = "Root-level dataset of PET reconstruction images"
        f.create_dataset("volume", data=np.zeros((4,), dtype=np.float32))
    return path


@pytest.fixture()
def short_desc_h5(tmp_path: Path) -> Path:
    """An fd5 file with a description shorter than 20 chars."""
    path = tmp_path / "short.h5"
    with h5py.File(path, "w") as f:
        f.attrs["description"] = "Root-level dataset of PET reconstruction images"
        ds = f.create_dataset("volume", data=np.zeros((4,), dtype=np.float32))
        ds.attrs["description"] = "short"
    return path


@pytest.fixture()
def placeholder_desc_h5(tmp_path: Path) -> Path:
    """An fd5 file with placeholder text in a description."""
    path = tmp_path / "placeholder.h5"
    with h5py.File(path, "w") as f:
        f.attrs["description"] = "Root-level dataset of PET reconstruction images"
        ds = f.create_dataset("volume", data=np.zeros((4,), dtype=np.float32))
        ds.attrs["description"] = "TODO fill this in later with real description"
    return path


@pytest.fixture()
def duplicate_desc_h5(tmp_path: Path) -> Path:
    """An fd5 file with duplicate descriptions on different items."""
    path = tmp_path / "duplicate.h5"
    with h5py.File(path, "w") as f:
        f.attrs["description"] = "Root-level dataset of PET reconstruction images"
        ds1 = f.create_dataset("volume", data=np.zeros((4,), dtype=np.float32))
        ds1.attrs["description"] = "Reconstructed image volume in Bq/mL units"
        ds2 = f.create_dataset("weights", data=np.ones((4,), dtype=np.float32))
        ds2.attrs["description"] = "Reconstructed image volume in Bq/mL units"
    return path


# ---------------------------------------------------------------------------
# check_descriptions — happy path
# ---------------------------------------------------------------------------


class TestCheckDescriptionsHappyPath:
    def test_clean_file_returns_empty_list(self, clean_h5: Path):
        warnings = check_descriptions(clean_h5)
        assert warnings == []

    def test_returns_list(self, clean_h5: Path):
        result = check_descriptions(clean_h5)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# check_descriptions — root description
# ---------------------------------------------------------------------------


class TestRootDescription:
    def test_missing_root_description(self, no_root_desc_h5: Path):
        warnings = check_descriptions(no_root_desc_h5)
        assert any(w.path == "/" and "missing" in w.message.lower() for w in warnings)

    def test_missing_root_description_severity(self, no_root_desc_h5: Path):
        warnings = check_descriptions(no_root_desc_h5)
        root_warnings = [w for w in warnings if w.path == "/"]
        assert root_warnings[0].severity == "error"

    def test_empty_root_description(self, empty_root_desc_h5: Path):
        warnings = check_descriptions(empty_root_desc_h5)
        assert any(w.path == "/" and "empty" in w.message.lower() for w in warnings)


# ---------------------------------------------------------------------------
# check_descriptions — groups and datasets
# ---------------------------------------------------------------------------


class TestGroupAndDatasetDescriptions:
    def test_missing_group_description(self, missing_group_desc_h5: Path):
        warnings = check_descriptions(missing_group_desc_h5)
        assert any(
            w.path == "/metadata" and "missing" in w.message.lower() for w in warnings
        )

    def test_missing_group_description_severity(self, missing_group_desc_h5: Path):
        warnings = check_descriptions(missing_group_desc_h5)
        meta_warnings = [w for w in warnings if w.path == "/metadata"]
        assert meta_warnings[0].severity == "error"

    def test_missing_dataset_description(self, missing_dataset_desc_h5: Path):
        warnings = check_descriptions(missing_dataset_desc_h5)
        assert any(
            w.path == "/volume" and "missing" in w.message.lower() for w in warnings
        )

    def test_missing_dataset_description_severity(self, missing_dataset_desc_h5: Path):
        warnings = check_descriptions(missing_dataset_desc_h5)
        vol_warnings = [w for w in warnings if w.path == "/volume"]
        assert vol_warnings[0].severity == "error"


# ---------------------------------------------------------------------------
# check_descriptions — short descriptions
# ---------------------------------------------------------------------------


class TestShortDescriptions:
    def test_short_description_warns(self, short_desc_h5: Path):
        warnings = check_descriptions(short_desc_h5)
        assert any(
            w.path == "/volume" and "short" in w.message.lower() for w in warnings
        )

    def test_short_description_severity(self, short_desc_h5: Path):
        warnings = check_descriptions(short_desc_h5)
        vol_warnings = [w for w in warnings if w.path == "/volume"]
        assert vol_warnings[0].severity == "warning"


# ---------------------------------------------------------------------------
# check_descriptions — placeholder text
# ---------------------------------------------------------------------------


class TestPlaceholderDescriptions:
    def test_placeholder_text_warns(self, placeholder_desc_h5: Path):
        warnings = check_descriptions(placeholder_desc_h5)
        assert any(
            w.path == "/volume" and "placeholder" in w.message.lower() for w in warnings
        )

    def test_placeholder_severity(self, placeholder_desc_h5: Path):
        warnings = check_descriptions(placeholder_desc_h5)
        vol_warnings = [w for w in warnings if w.path == "/volume"]
        assert vol_warnings[0].severity == "warning"


# ---------------------------------------------------------------------------
# check_descriptions — duplicate descriptions
# ---------------------------------------------------------------------------


class TestDuplicateDescriptions:
    def test_duplicate_descriptions_warn(self, duplicate_desc_h5: Path):
        warnings = check_descriptions(duplicate_desc_h5)
        assert any("duplicate" in w.message.lower() for w in warnings)

    def test_duplicate_severity(self, duplicate_desc_h5: Path):
        warnings = check_descriptions(duplicate_desc_h5)
        dup_warnings = [w for w in warnings if "duplicate" in w.message.lower()]
        assert all(w.severity == "warning" for w in dup_warnings)


# ---------------------------------------------------------------------------
# check_descriptions — nested structures
# ---------------------------------------------------------------------------


class TestNestedStructures:
    def test_nested_group_missing_description(self, tmp_path: Path):
        path = tmp_path / "nested.h5"
        with h5py.File(path, "w") as f:
            f.attrs["description"] = "Root-level dataset of PET reconstruction images"
            g = f.create_group("metadata")
            g.attrs["description"] = "Reconstruction parameters and settings"
            g.create_group("reconstruction")  # no description
        warnings = check_descriptions(path)
        assert any(
            w.path == "/metadata/reconstruction" and "missing" in w.message.lower()
            for w in warnings
        )

    def test_nested_dataset_missing_description(self, tmp_path: Path):
        path = tmp_path / "nested_ds.h5"
        with h5py.File(path, "w") as f:
            f.attrs["description"] = "Root-level dataset of PET reconstruction images"
            g = f.create_group("data")
            g.attrs["description"] = "Primary data group for measurements"
            g.create_dataset("values", data=np.zeros((4,)))  # no description
        warnings = check_descriptions(path)
        assert any(
            w.path == "/data/values" and "missing" in w.message.lower()
            for w in warnings
        )


# ---------------------------------------------------------------------------
# Warning dataclass
# ---------------------------------------------------------------------------


class TestWarningDataclass:
    def test_warning_fields(self):
        w = Warning(path="/volume", message="test message", severity="warning")
        assert w.path == "/volume"
        assert w.message == "test message"
        assert w.severity == "warning"

    def test_warning_equality(self):
        w1 = Warning(path="/a", message="msg", severity="error")
        w2 = Warning(path="/a", message="msg", severity="error")
        assert w1 == w2


# ---------------------------------------------------------------------------
# CLI: fd5 check-descriptions
# ---------------------------------------------------------------------------


class TestCheckDescriptionsCLI:
    def test_clean_file_exits_zero(self, runner: CliRunner, clean_h5: Path):
        result = runner.invoke(cli, ["check-descriptions", str(clean_h5)])
        assert result.exit_code == 0

    def test_clean_file_shows_ok(self, runner: CliRunner, clean_h5: Path):
        result = runner.invoke(cli, ["check-descriptions", str(clean_h5)])
        assert "ok" in result.output.lower() or "pass" in result.output.lower()

    def test_missing_desc_exits_nonzero(self, runner: CliRunner, no_root_desc_h5: Path):
        result = runner.invoke(cli, ["check-descriptions", str(no_root_desc_h5)])
        assert result.exit_code != 0

    def test_missing_desc_shows_warnings(
        self, runner: CliRunner, no_root_desc_h5: Path
    ):
        result = runner.invoke(cli, ["check-descriptions", str(no_root_desc_h5)])
        assert "missing" in result.output.lower() or "warning" in result.output.lower()

    def test_nonexistent_file_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["check-descriptions", str(tmp_path / "ghost.h5")])
        assert result.exit_code != 0

    def test_short_desc_exits_nonzero(self, runner: CliRunner, short_desc_h5: Path):
        result = runner.invoke(cli, ["check-descriptions", str(short_desc_h5)])
        assert result.exit_code != 0

    def test_placeholder_desc_exits_nonzero(
        self, runner: CliRunner, placeholder_desc_h5: Path
    ):
        result = runner.invoke(cli, ["check-descriptions", str(placeholder_desc_h5)])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Placeholder patterns
# ---------------------------------------------------------------------------


class TestPlaceholderPatterns:
    """Verify multiple placeholder patterns are caught."""

    @pytest.mark.parametrize(
        "text",
        [
            "TBD - will add later for this field",
            "FIXME need a real description here",
            "placeholder text for the field here",
            "PLACEHOLDER for the description field",
            "description goes here eventually soon",
            "xxx fill this in with actual content",
        ],
    )
    def test_various_placeholders(self, tmp_path: Path, text: str):
        path = tmp_path / "ph.h5"
        with h5py.File(path, "w") as f:
            f.attrs["description"] = "Root-level dataset of PET reconstruction images"
            ds = f.create_dataset("volume", data=np.zeros((4,), dtype=np.float32))
            ds.attrs["description"] = text
        warnings = check_descriptions(path)
        assert any(
            w.path == "/volume" and "placeholder" in w.message.lower() for w in warnings
        )
