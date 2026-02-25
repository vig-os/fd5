"""Tests for fd5 ingest CLI commands — issue #113."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from click.testing import CliRunner

from fd5.cli import cli


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def binary_file(tmp_path: Path) -> Path:
    """Create a small raw binary file (float32, 4x4x4)."""
    arr = np.ones((4, 4, 4), dtype=np.float32)
    path = tmp_path / "data.bin"
    arr.tofile(path)
    return path


@pytest.fixture()
def csv_file(tmp_path: Path) -> Path:
    """Create a minimal CSV file with energy + counts columns."""
    path = tmp_path / "spectrum.csv"
    path.write_text("energy,counts\n1.0,100\n2.0,200\n3.0,300\n")
    return path


# ---------------------------------------------------------------------------
# fd5 ingest --help
# ---------------------------------------------------------------------------


class TestIngestHelp:
    def test_ingest_help_exits_zero(self, runner: CliRunner):
        result = runner.invoke(cli, ["ingest", "--help"])
        assert result.exit_code == 0

    def test_ingest_help_lists_subcommands(self, runner: CliRunner):
        result = runner.invoke(cli, ["ingest", "--help"])
        for sub in ("raw", "nifti", "csv", "list", "parquet"):
            assert sub in result.output

    def test_ingest_appears_in_main_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert "ingest" in result.output


# ---------------------------------------------------------------------------
# fd5 ingest list
# ---------------------------------------------------------------------------


class TestIngestList:
    def test_exits_zero(self, runner: CliRunner):
        result = runner.invoke(cli, ["ingest", "list"])
        assert result.exit_code == 0

    def test_shows_header(self, runner: CliRunner):
        result = runner.invoke(cli, ["ingest", "list"])
        assert "available" in result.output.lower() or "loader" in result.output.lower()

    def test_shows_raw_loader(self, runner: CliRunner):
        with patch(
            "fd5.cli.discover_loaders",
            return_value={"raw": MagicMock()},
        ):
            result = runner.invoke(cli, ["ingest", "list"])
            assert "raw" in result.output

    def test_shows_missing_dep(self, runner: CliRunner):
        """Loaders not returned by discover_loaders are shown as missing."""
        with (
            patch(
                "fd5.cli.discover_loaders",
                return_value={},
            ),
            patch(
                "fd5.cli._ALL_LOADER_NAMES",
                ("raw", "nifti", "csv"),
            ),
        ):
            result = runner.invoke(cli, ["ingest", "list"])
            assert "raw" in result.output


# ---------------------------------------------------------------------------
# fd5 ingest raw
# ---------------------------------------------------------------------------


def _make_mock_ingest_binary(tmp_path: Path):
    """Return a patch that replaces ingest_binary with a mock."""
    fake_h5 = tmp_path / "out" / "result.h5"
    fake_h5.parent.mkdir(exist_ok=True)
    fake_h5.touch()
    return patch("fd5.cli._ingest_binary", return_value=fake_h5)


class TestIngestRaw:
    def test_exits_zero(self, runner: CliRunner, binary_file: Path, tmp_path: Path):
        with _make_mock_ingest_binary(tmp_path):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "raw",
                    str(binary_file),
                    "--output",
                    str(tmp_path / "out"),
                    "--name",
                    "Test Raw",
                    "--description",
                    "Test raw binary ingest",
                    "--product",
                    "recon",
                    "--dtype",
                    "float32",
                    "--shape",
                    "4,4,4",
                ],
            )
        assert result.exit_code == 0, result.output

    def test_prints_confirmation(
        self, runner: CliRunner, binary_file: Path, tmp_path: Path
    ):
        with _make_mock_ingest_binary(tmp_path):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "raw",
                    str(binary_file),
                    "--output",
                    str(tmp_path / "out"),
                    "--name",
                    "Test",
                    "--description",
                    "desc",
                    "--product",
                    "recon",
                    "--dtype",
                    "float32",
                    "--shape",
                    "4,4,4",
                ],
            )
        assert "ingested" in result.output.lower() or ".h5" in result.output.lower()

    def test_calls_ingest_binary_with_correct_args(
        self, runner: CliRunner, binary_file: Path, tmp_path: Path
    ):
        with _make_mock_ingest_binary(tmp_path) as mock_fn:
            runner.invoke(
                cli,
                [
                    "ingest",
                    "raw",
                    str(binary_file),
                    "--output",
                    str(tmp_path / "out"),
                    "--name",
                    "N",
                    "--description",
                    "D",
                    "--product",
                    "recon",
                    "--dtype",
                    "float32",
                    "--shape",
                    "4,4,4",
                ],
            )
        mock_fn.assert_called_once()
        _, kwargs = mock_fn.call_args
        assert kwargs["dtype"] == "float32"
        assert kwargs["shape"] == (4, 4, 4)
        assert kwargs["product"] == "recon"
        assert kwargs["name"] == "N"

    def test_missing_required_options(self, runner: CliRunner, binary_file: Path):
        result = runner.invoke(cli, ["ingest", "raw", str(binary_file)])
        assert result.exit_code != 0

    def test_nonexistent_source_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            cli,
            [
                "ingest",
                "raw",
                str(tmp_path / "ghost.bin"),
                "--output",
                str(tmp_path),
                "--name",
                "x",
                "--description",
                "x",
                "--product",
                "recon",
                "--dtype",
                "float32",
                "--shape",
                "4,4,4",
            ],
        )
        assert result.exit_code != 0

    def test_error_from_ingest_binary_exits_nonzero(
        self, runner: CliRunner, binary_file: Path, tmp_path: Path
    ):
        out = tmp_path / "out"
        out.mkdir()
        with patch(
            "fd5.cli._ingest_binary",
            side_effect=ValueError("cannot reshape"),
        ):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "raw",
                    str(binary_file),
                    "--output",
                    str(out),
                    "--name",
                    "x",
                    "--description",
                    "x",
                    "--product",
                    "recon",
                    "--dtype",
                    "float32",
                    "--shape",
                    "999,999,999",
                ],
            )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fd5 ingest csv
# ---------------------------------------------------------------------------


class TestIngestCsv:
    def test_exits_zero(self, runner: CliRunner, csv_file: Path, tmp_path: Path):
        out = tmp_path / "out"
        out.mkdir()
        result = runner.invoke(
            cli,
            [
                "ingest",
                "csv",
                str(csv_file),
                "--output",
                str(out),
                "--name",
                "Test Spectrum",
                "--description",
                "Test CSV ingest",
                "--product",
                "spectrum",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_creates_h5_file(self, runner: CliRunner, csv_file: Path, tmp_path: Path):
        out = tmp_path / "out"
        out.mkdir()
        runner.invoke(
            cli,
            [
                "ingest",
                "csv",
                str(csv_file),
                "--output",
                str(out),
                "--name",
                "Test",
                "--description",
                "desc",
                "--product",
                "spectrum",
            ],
        )
        h5_files = list(out.glob("*.h5"))
        assert len(h5_files) >= 1

    def test_prints_confirmation(
        self, runner: CliRunner, csv_file: Path, tmp_path: Path
    ):
        out = tmp_path / "out"
        out.mkdir()
        result = runner.invoke(
            cli,
            [
                "ingest",
                "csv",
                str(csv_file),
                "--output",
                str(out),
                "--name",
                "Test",
                "--description",
                "desc",
                "--product",
                "spectrum",
            ],
        )
        assert "ingested" in result.output.lower() or ".h5" in result.output.lower()

    def test_custom_delimiter(self, runner: CliRunner, tmp_path: Path):
        tsv = tmp_path / "data.tsv"
        tsv.write_text("energy\tcounts\n1.0\t100\n2.0\t200\n")
        out = tmp_path / "out"
        out.mkdir()
        result = runner.invoke(
            cli,
            [
                "ingest",
                "csv",
                str(tsv),
                "--output",
                str(out),
                "--name",
                "TSV",
                "--description",
                "tab-delimited",
                "--product",
                "spectrum",
                "--delimiter",
                "\t",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_missing_source_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            cli,
            [
                "ingest",
                "csv",
                str(tmp_path / "ghost.csv"),
                "--output",
                str(tmp_path),
                "--name",
                "x",
                "--description",
                "x",
                "--product",
                "spectrum",
            ],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fd5 ingest nifti
# ---------------------------------------------------------------------------


class TestIngestNifti:
    def test_exits_zero_with_mock(self, runner: CliRunner, tmp_path: Path):
        """Nifti ingest works when nibabel is available (mocked)."""
        mock_loader = MagicMock()
        fake_h5 = tmp_path / "out" / "result.h5"
        (tmp_path / "out").mkdir()
        fake_h5.touch()
        mock_loader.ingest.return_value = fake_h5

        nii = tmp_path / "vol.nii"
        nii.touch()

        with patch("fd5.cli._get_nifti_loader", return_value=mock_loader):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "nifti",
                    str(nii),
                    "--output",
                    str(tmp_path / "out"),
                    "--name",
                    "CT Volume",
                    "--description",
                    "Thorax CT scan",
                ],
            )
        assert result.exit_code == 0, result.output

    def test_missing_nibabel_shows_error(self, runner: CliRunner, tmp_path: Path):
        nii = tmp_path / "vol.nii"
        nii.touch()
        out = tmp_path / "out"
        out.mkdir()

        with patch("fd5.cli._get_nifti_loader", side_effect=ImportError("no nibabel")):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "nifti",
                    str(nii),
                    "--output",
                    str(out),
                    "--name",
                    "CT",
                    "--description",
                    "desc",
                ],
            )
        assert result.exit_code != 0
        assert "nibabel" in result.output.lower() or "install" in result.output.lower()

    def test_nonexistent_source_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            cli,
            [
                "ingest",
                "nifti",
                str(tmp_path / "ghost.nii"),
                "--output",
                str(tmp_path),
                "--name",
                "x",
                "--description",
                "x",
            ],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fd5 ingest dicom (always mocked — no pydicom loader yet)
# ---------------------------------------------------------------------------


class TestIngestDicom:
    def test_exits_zero_with_mock(self, runner: CliRunner, tmp_path: Path):
        mock_loader = MagicMock()
        fake_h5 = tmp_path / "out" / "result.h5"
        (tmp_path / "out").mkdir()
        fake_h5.touch()
        mock_loader.ingest.return_value = fake_h5

        dcm_dir = tmp_path / "dcm"
        dcm_dir.mkdir()

        with patch("fd5.cli._get_dicom_loader", return_value=mock_loader):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "dicom",
                    str(dcm_dir),
                    "--output",
                    str(tmp_path / "out"),
                    "--name",
                    "PET Recon",
                    "--description",
                    "Whole-body PET",
                ],
            )
        assert result.exit_code == 0, result.output

    def test_missing_pydicom_shows_error(self, runner: CliRunner, tmp_path: Path):
        dcm_dir = tmp_path / "dcm"
        dcm_dir.mkdir()
        out = tmp_path / "out"
        out.mkdir()

        with patch(
            "fd5.cli._get_dicom_loader",
            side_effect=ImportError("no pydicom"),
        ):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "dicom",
                    str(dcm_dir),
                    "--output",
                    str(out),
                    "--name",
                    "PET",
                    "--description",
                    "desc",
                ],
            )
        assert result.exit_code != 0
        assert "pydicom" in result.output.lower() or "install" in result.output.lower()


# ---------------------------------------------------------------------------
# fd5 ingest parquet
# ---------------------------------------------------------------------------


@pytest.fixture()
def parquet_file(tmp_path: Path) -> Path:
    """Create a minimal Parquet file with energy + counts columns."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table({"energy": [1.0, 2.0, 3.0], "counts": [100, 200, 300]})
    path = tmp_path / "spectrum.parquet"
    pq.write_table(table, path)
    return path


class TestIngestParquet:
    def test_exits_zero_with_mock(self, runner: CliRunner, tmp_path: Path):
        mock_loader = MagicMock()
        fake_h5 = tmp_path / "out" / "result.h5"
        (tmp_path / "out").mkdir()
        fake_h5.touch()
        mock_loader.ingest.return_value = fake_h5

        pq_file = tmp_path / "data.parquet"
        pq_file.touch()

        with patch("fd5.cli._get_parquet_loader", return_value=mock_loader):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "parquet",
                    str(pq_file),
                    "--output",
                    str(tmp_path / "out"),
                    "--name",
                    "Gamma spectrum",
                    "--description",
                    "HPGe detector measurement",
                    "--product",
                    "spectrum",
                ],
            )
        assert result.exit_code == 0, result.output

    def test_prints_confirmation(self, runner: CliRunner, tmp_path: Path):
        mock_loader = MagicMock()
        fake_h5 = tmp_path / "out" / "result.h5"
        (tmp_path / "out").mkdir()
        fake_h5.touch()
        mock_loader.ingest.return_value = fake_h5

        pq_file = tmp_path / "data.parquet"
        pq_file.touch()

        with patch("fd5.cli._get_parquet_loader", return_value=mock_loader):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "parquet",
                    str(pq_file),
                    "--output",
                    str(tmp_path / "out"),
                    "--name",
                    "Test",
                    "--description",
                    "desc",
                    "--product",
                    "spectrum",
                ],
            )
        assert "ingested" in result.output.lower() or ".h5" in result.output.lower()

    def test_passes_column_map(self, runner: CliRunner, tmp_path: Path):
        mock_loader = MagicMock()
        fake_h5 = tmp_path / "out" / "result.h5"
        (tmp_path / "out").mkdir()
        fake_h5.touch()
        mock_loader.ingest.return_value = fake_h5

        pq_file = tmp_path / "data.parquet"
        pq_file.touch()

        col_map = '{"en": "energy", "ct": "counts"}'
        with patch("fd5.cli._get_parquet_loader", return_value=mock_loader):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "parquet",
                    str(pq_file),
                    "--output",
                    str(tmp_path / "out"),
                    "--name",
                    "Test",
                    "--description",
                    "desc",
                    "--product",
                    "spectrum",
                    "--column-map",
                    col_map,
                ],
            )
        assert result.exit_code == 0, result.output
        _, kwargs = mock_loader.ingest.call_args
        assert kwargs["column_map"] == {"en": "energy", "ct": "counts"}

    def test_missing_pyarrow_shows_error(self, runner: CliRunner, tmp_path: Path):
        pq_file = tmp_path / "data.parquet"
        pq_file.touch()
        out = tmp_path / "out"
        out.mkdir()

        with patch(
            "fd5.cli._get_parquet_loader",
            side_effect=ImportError("no pyarrow"),
        ):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "parquet",
                    str(pq_file),
                    "--output",
                    str(out),
                    "--name",
                    "Test",
                    "--description",
                    "desc",
                    "--product",
                    "spectrum",
                ],
            )
        assert result.exit_code != 0
        assert "pyarrow" in result.output.lower() or "install" in result.output.lower()

    def test_nonexistent_source_exits_nonzero(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            cli,
            [
                "ingest",
                "parquet",
                str(tmp_path / "ghost.parquet"),
                "--output",
                str(tmp_path),
                "--name",
                "x",
                "--description",
                "x",
                "--product",
                "spectrum",
            ],
        )
        assert result.exit_code != 0

    def test_ingest_list_shows_parquet(self, runner: CliRunner):
        with patch(
            "fd5.cli.discover_loaders",
            return_value={"parquet": MagicMock()},
        ):
            result = runner.invoke(cli, ["ingest", "list"])
            assert "parquet" in result.output
