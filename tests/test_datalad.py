"""Tests for fd5.datalad — DataLad integration hooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import h5py
import pytest

from fd5.h5io import dict_to_h5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_h5(
    path: Path,
    root_attrs: dict[str, Any],
    groups: dict[str, dict[str, Any]] | None = None,
) -> None:
    with h5py.File(path, "w") as f:
        dict_to_h5(f, root_attrs)
        if groups:
            for name, attrs in groups.items():
                g = f.create_group(name)
                dict_to_h5(g, attrs)


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
}


@pytest.fixture()
def full_h5(tmp_path: Path) -> Path:
    path = tmp_path / "recon-aabb1122.h5"
    _create_h5(
        path,
        root_attrs={
            "_schema_version": 1,
            "product": "recon",
            "id": "sha256:aabb112233445566",
            "content_hash": "sha256:deadbeef",
            "timestamp": "2024-07-24T19:06:10+02:00",
            "name": "DOGPLET DD01 Recon",
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
    return path


@pytest.fixture()
def minimal_h5(tmp_path: Path) -> Path:
    path = tmp_path / "sim-11223344.h5"
    _create_h5(
        path,
        root_attrs={
            "_schema_version": 1,
            "product": "sim",
            "id": "sha256:1122334455667788",
            "content_hash": "sha256:00000000",
            "timestamp": "2025-06-01T12:00:00Z",
        },
    )
    return path


# ---------------------------------------------------------------------------
# extract_metadata()
# ---------------------------------------------------------------------------


class TestExtractMetadata:
    def test_returns_dict(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(full_h5)
        assert isinstance(result, dict)

    def test_has_title(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(full_h5)
        assert result["title"] == "DOGPLET DD01 Recon"

    def test_has_product(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(full_h5)
        assert result["product"] == "recon"

    def test_has_id(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(full_h5)
        assert result["id"] == "sha256:aabb112233445566"

    def test_has_timestamp(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(full_h5)
        assert result["timestamp"] == "2024-07-24T19:06:10+02:00"

    def test_has_content_hash(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(full_h5)
        assert result["content_hash"] == "sha256:deadbeef"

    def test_has_creators(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(full_h5)
        assert len(result["creators"]) == 2
        names = {c["name"] for c in result["creators"]}
        assert names == {"Jane Doe", "John Smith"}

    def test_creator_has_affiliation(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(full_h5)
        jane = next(c for c in result["creators"] if c["name"] == "Jane Doe")
        assert jane["affiliation"] == "ETH Zurich"

    def test_creator_has_orcid(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(full_h5)
        jane = next(c for c in result["creators"] if c["name"] == "Jane Doe")
        assert jane["orcid"] == "https://orcid.org/0000-0002-1234-5678"

    def test_creator_without_orcid(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(full_h5)
        john = next(c for c in result["creators"] if c["name"] == "John Smith")
        assert "orcid" not in john

    def test_title_falls_back_to_stem(self, minimal_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(minimal_h5)
        assert result["title"] == "sim-11223344"

    def test_no_creators_when_no_study(self, minimal_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(minimal_h5)
        assert "creators" not in result

    def test_accepts_string_path(self, full_h5: Path):
        from fd5.datalad import extract_metadata

        result = extract_metadata(str(full_h5))
        assert result["product"] == "recon"


class TestExtractMetadataEdgeCases:
    def test_no_study_creators_key(self, tmp_path: Path):
        """Study group exists but has no creators sub-group."""
        from fd5.datalad import extract_metadata

        path = tmp_path / "no-creators.h5"
        _create_h5(
            path,
            root_attrs={"_schema_version": 1, "product": "recon"},
            groups={"study": {"name": "Test"}},
        )
        result = extract_metadata(path)
        assert "creators" not in result

    def test_non_dict_creator_entry_skipped(self, tmp_path: Path):
        """Non-dict entry in creators group is skipped."""
        from fd5.datalad import extract_metadata

        path = tmp_path / "bad-creator.h5"
        with h5py.File(path, "w") as f:
            dict_to_h5(f, {"_schema_version": 1, "product": "recon"})
            study = f.create_group("study")
            study.attrs["name"] = "Test"
            creators = study.create_group("creators")
            creators.attrs["bad_entry"] = "not-a-dict"
            good = creators.create_group("good_entry")
            good.attrs["name"] = "Good Person"

        result = extract_metadata(path)
        assert len(result["creators"]) == 1
        assert result["creators"][0]["name"] == "Good Person"

    def test_missing_optional_attrs(self, tmp_path: Path):
        """File with only _schema_version — no product, id, etc."""
        from fd5.datalad import extract_metadata

        path = tmp_path / "bare.h5"
        _create_h5(path, root_attrs={"_schema_version": 1})
        result = extract_metadata(path)
        assert "product" not in result
        assert "id" not in result
        assert "timestamp" not in result
        assert "content_hash" not in result
        assert result["title"] == "bare"


# ---------------------------------------------------------------------------
# _has_datalad()
# ---------------------------------------------------------------------------


class TestHasDatalad:
    def test_returns_false_when_not_installed(self):
        from fd5.datalad import _has_datalad

        with patch.dict("sys.modules", {"datalad": None}):
            assert _has_datalad() is False

    def test_returns_true_when_installed(self):
        from fd5.datalad import _has_datalad

        mock_datalad = MagicMock()
        with patch.dict("sys.modules", {"datalad": mock_datalad}):
            assert _has_datalad() is True


# ---------------------------------------------------------------------------
# register_with_datalad()
# ---------------------------------------------------------------------------


class TestRegisterWithDatalad:
    def test_raises_import_error_when_no_datalad(self, full_h5: Path):
        from fd5.datalad import register_with_datalad

        with patch("fd5.datalad._has_datalad", return_value=False):
            with pytest.raises(ImportError, match="datalad is not installed"):
                register_with_datalad(full_h5)

    def test_success_with_mocked_datalad(self, full_h5: Path):
        from fd5.datalad import register_with_datalad

        mock_ds = MagicMock()
        mock_dl_api = MagicMock()
        mock_dl_api.Dataset.return_value = mock_ds

        with (
            patch("fd5.datalad._has_datalad", return_value=True),
            patch.dict(
                "sys.modules",
                {"datalad": MagicMock(), "datalad.api": mock_dl_api},
            ),
        ):
            result = register_with_datalad(full_h5)

        assert result["status"] == "ok"
        assert result["path"] == str(full_h5)
        assert "metadata" in result
        assert result["metadata"]["product"] == "recon"

    def test_uses_parent_dir_when_no_dataset_path(self, full_h5: Path):
        from fd5.datalad import register_with_datalad

        mock_ds = MagicMock()
        mock_dl_api = MagicMock()
        mock_dl_api.Dataset.return_value = mock_ds

        with (
            patch("fd5.datalad._has_datalad", return_value=True),
            patch.dict(
                "sys.modules",
                {"datalad": MagicMock(), "datalad.api": mock_dl_api},
            ),
        ):
            result = register_with_datalad(full_h5)

        assert result["dataset"] == str(full_h5.parent)
        mock_dl_api.Dataset.assert_called_once_with(str(full_h5.parent))

    def test_uses_explicit_dataset_path(self, full_h5: Path, tmp_path: Path):
        from fd5.datalad import register_with_datalad

        ds_path = tmp_path / "my-dataset"
        ds_path.mkdir()

        mock_ds = MagicMock()
        mock_dl_api = MagicMock()
        mock_dl_api.Dataset.return_value = mock_ds

        with (
            patch("fd5.datalad._has_datalad", return_value=True),
            patch.dict(
                "sys.modules",
                {"datalad": MagicMock(), "datalad.api": mock_dl_api},
            ),
        ):
            result = register_with_datalad(full_h5, ds_path)

        assert result["dataset"] == str(ds_path)
        mock_dl_api.Dataset.assert_called_once_with(str(ds_path))

    def test_calls_save_with_message(self, full_h5: Path):
        from fd5.datalad import register_with_datalad

        mock_ds = MagicMock()
        mock_dl_api = MagicMock()
        mock_dl_api.Dataset.return_value = mock_ds

        with (
            patch("fd5.datalad._has_datalad", return_value=True),
            patch.dict(
                "sys.modules",
                {"datalad": MagicMock(), "datalad.api": mock_dl_api},
            ),
        ):
            register_with_datalad(full_h5)

        mock_ds.save.assert_called_once()
        call_args = mock_ds.save.call_args
        assert full_h5.name in call_args.kwargs.get(
            "message", call_args.args[1] if len(call_args.args) > 1 else ""
        )

    def test_accepts_string_paths(self, full_h5: Path):
        from fd5.datalad import register_with_datalad

        mock_ds = MagicMock()
        mock_dl_api = MagicMock()
        mock_dl_api.Dataset.return_value = mock_ds

        with (
            patch("fd5.datalad._has_datalad", return_value=True),
            patch.dict(
                "sys.modules",
                {"datalad": MagicMock(), "datalad.api": mock_dl_api},
            ),
        ):
            result = register_with_datalad(str(full_h5), str(full_h5.parent))

        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# CLI: fd5 datalad-register
# ---------------------------------------------------------------------------


class TestDataladRegisterCLI:
    def test_success_with_mocked_datalad(self, full_h5: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        mock_ds = MagicMock()
        mock_dl_api = MagicMock()
        mock_dl_api.Dataset.return_value = mock_ds

        runner = CliRunner()
        with (
            patch("fd5.datalad._has_datalad", return_value=True),
            patch.dict(
                "sys.modules",
                {"datalad": MagicMock(), "datalad.api": mock_dl_api},
            ),
        ):
            result = runner.invoke(cli, ["datalad-register", str(full_h5)])

        assert result.exit_code == 0, result.output
        assert "Registered" in result.output

    def test_shows_metadata_fields(self, full_h5: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        mock_ds = MagicMock()
        mock_dl_api = MagicMock()
        mock_dl_api.Dataset.return_value = mock_ds

        runner = CliRunner()
        with (
            patch("fd5.datalad._has_datalad", return_value=True),
            patch.dict(
                "sys.modules",
                {"datalad": MagicMock(), "datalad.api": mock_dl_api},
            ),
        ):
            result = runner.invoke(cli, ["datalad-register", str(full_h5)])

        assert "recon" in result.output
        assert "sha256:" in result.output

    def test_with_dataset_option(self, full_h5: Path, tmp_path: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        ds_path = tmp_path / "ds"
        ds_path.mkdir()

        mock_ds = MagicMock()
        mock_dl_api = MagicMock()
        mock_dl_api.Dataset.return_value = mock_ds

        runner = CliRunner()
        with (
            patch("fd5.datalad._has_datalad", return_value=True),
            patch.dict(
                "sys.modules",
                {"datalad": MagicMock(), "datalad.api": mock_dl_api},
            ),
        ):
            result = runner.invoke(
                cli,
                ["datalad-register", str(full_h5), "--dataset", str(ds_path)],
            )

        assert result.exit_code == 0, result.output

    def test_error_when_datalad_not_installed(self, full_h5: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        runner = CliRunner()
        with patch("fd5.datalad._has_datalad", return_value=False):
            result = runner.invoke(cli, ["datalad-register", str(full_h5)])

        assert result.exit_code == 1
        assert "datalad is not installed" in result.output

    def test_nonexistent_file_exits_nonzero(self, tmp_path: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["datalad-register", str(tmp_path / "ghost.h5")])
        assert result.exit_code != 0

    def test_generic_error_exits_nonzero(self, full_h5: Path):
        from click.testing import CliRunner

        from fd5.cli import cli

        runner = CliRunner()
        with (
            patch("fd5.datalad._has_datalad", return_value=True),
            patch(
                "fd5.datalad.register_with_datalad",
                side_effect=RuntimeError("something broke"),
            ),
        ):
            result = runner.invoke(cli, ["datalad-register", str(full_h5)])

        assert result.exit_code == 1
        assert "something broke" in result.output

    def test_appears_in_help(self):
        from click.testing import CliRunner

        from fd5.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "datalad-register" in result.output
