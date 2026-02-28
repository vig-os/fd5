"""Tests for fd5.ingest.csv — CSV/TSV tabular data loader."""

from __future__ import annotations

import hashlib
from pathlib import Path

import h5py
import numpy as np
import pytest

from fd5.ingest._base import Loader
from fd5.ingest.csv import CsvLoader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def loader() -> CsvLoader:
    return CsvLoader()


@pytest.fixture()
def spectrum_csv(tmp_path: Path) -> Path:
    """Simple two-column spectrum CSV: energy, counts."""
    p = tmp_path / "spectrum.csv"
    p.write_text(
        "# units: keV\n"
        "# detector: HPGe\n"
        "energy,counts\n"
        "100.0,10\n"
        "200.0,25\n"
        "300.0,18\n"
        "400.0,7\n"
    )
    return p


@pytest.fixture()
def calibration_csv(tmp_path: Path) -> Path:
    """Three-column calibration CSV: input, output, uncertainty."""
    p = tmp_path / "calibration.csv"
    p.write_text("input,output,uncertainty\n1.0,2.1,0.1\n2.0,4.0,0.2\n3.0,6.2,0.15\n")
    return p


@pytest.fixture()
def device_data_tsv(tmp_path: Path) -> Path:
    """Tab-delimited device data: timestamp, temperature, pressure."""
    p = tmp_path / "device.tsv"
    p.write_text(
        "timestamp\ttemperature\tpressure\n"
        "0.0\t22.5\t101.3\n"
        "1.0\t22.6\t101.2\n"
        "2.0\t22.4\t101.4\n"
    )
    return p


@pytest.fixture()
def comment_metadata_csv(tmp_path: Path) -> Path:
    """CSV with comment-line metadata."""
    p = tmp_path / "annotated.csv"
    p.write_text(
        "# units: keV\n"
        "# detector: HPGe\n"
        "# facility: PSI\n"
        "# measurement_id: M-2026-001\n"
        "energy,counts\n"
        "100.0,50\n"
        "200.0,75\n"
    )
    return p


@pytest.fixture()
def empty_data_csv(tmp_path: Path) -> Path:
    """CSV with header but no data rows."""
    p = tmp_path / "empty.csv"
    p.write_text("energy,counts\n")
    return p


@pytest.fixture()
def mixed_types_csv(tmp_path: Path) -> Path:
    """CSV with numeric and string columns."""
    p = tmp_path / "mixed.csv"
    p.write_text("channel,counts,label\n1,100,low\n2,250,mid\n3,50,high\n")
    return p


# ---------------------------------------------------------------------------
# Loader protocol conformance
# ---------------------------------------------------------------------------


class TestCsvLoaderProtocol:
    """CsvLoader satisfies the Loader protocol."""

    def test_is_loader_instance(self, loader: CsvLoader):
        assert isinstance(loader, Loader)

    def test_supported_product_types(self, loader: CsvLoader):
        types = loader.supported_product_types
        assert isinstance(types, list)
        assert "spectrum" in types
        assert "calibration" in types
        assert "device_data" in types

    def test_has_ingest_method(self, loader: CsvLoader):
        assert callable(getattr(loader, "ingest", None))


# ---------------------------------------------------------------------------
# CSV reading — happy path
# ---------------------------------------------------------------------------


class TestIngestSpectrum:
    """Ingest spectrum CSV produces valid fd5 file."""

    def test_returns_path(self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path):
        result = loader.ingest(
            spectrum_csv,
            tmp_path / "out",
            product="spectrum",
            name="Test spectrum",
            description="A test spectrum from CSV",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        assert isinstance(result, Path)
        assert result.exists()
        assert result.suffix == ".h5"

    def test_root_attrs(self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path):
        result = loader.ingest(
            spectrum_csv,
            tmp_path / "out",
            product="spectrum",
            name="Test spectrum",
            description="A test spectrum from CSV",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "spectrum"
            assert f.attrs["name"] == "Test spectrum"
            assert f.attrs["description"] == "A test spectrum from CSV"

    def test_data_written(self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path):
        result = loader.ingest(
            spectrum_csv,
            tmp_path / "out",
            product="spectrum",
            name="Test spectrum",
            description="A test spectrum from CSV",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            assert "counts" in f
            counts = f["counts"][:]
            assert counts.shape == (4,)
            np.testing.assert_array_almost_equal(counts, [10, 25, 18, 7])


class TestIngestCalibration:
    """Ingest calibration CSV produces valid fd5 file."""

    def test_returns_path(
        self, loader: CsvLoader, calibration_csv: Path, tmp_path: Path
    ):
        result = loader.ingest(
            calibration_csv,
            tmp_path / "out",
            product="calibration",
            name="Energy cal",
            description="Energy calibration curve",
            timestamp="2026-02-25T12:00:00+00:00",
            calibration_type="energy_calibration",
            scanner_model="TestScanner",
            scanner_serial="SN-001",
            valid_from="2026-01-01",
            valid_until="2027-01-01",
        )
        assert isinstance(result, Path)
        assert result.exists()

    def test_calibration_attrs(
        self, loader: CsvLoader, calibration_csv: Path, tmp_path: Path
    ):
        result = loader.ingest(
            calibration_csv,
            tmp_path / "out",
            product="calibration",
            name="Energy cal",
            description="Energy calibration curve",
            timestamp="2026-02-25T12:00:00+00:00",
            calibration_type="energy_calibration",
            scanner_model="TestScanner",
            scanner_serial="SN-001",
            valid_from="2026-01-01",
            valid_until="2027-01-01",
        )
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "calibration"


class TestIngestDeviceData:
    """Ingest TSV device data produces valid fd5 file."""

    def test_tsv_delimiter(
        self, loader: CsvLoader, device_data_tsv: Path, tmp_path: Path
    ):
        result = loader.ingest(
            device_data_tsv,
            tmp_path / "out",
            product="device_data",
            name="Temp log",
            description="Temperature logger data",
            timestamp="2026-02-25T12:00:00+00:00",
            delimiter="\t",
            device_type="environmental_sensor",
            device_model="TempSensor-100",
        )
        assert isinstance(result, Path)
        assert result.exists()

    def test_device_data_attrs(
        self, loader: CsvLoader, device_data_tsv: Path, tmp_path: Path
    ):
        result = loader.ingest(
            device_data_tsv,
            tmp_path / "out",
            product="device_data",
            name="Temp log",
            description="Temperature logger data",
            timestamp="2026-02-25T12:00:00+00:00",
            delimiter="\t",
            device_type="environmental_sensor",
            device_model="TempSensor-100",
        )
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "device_data"


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------


class TestColumnMapping:
    """Column mapping configurable and auto-detected from headers."""

    def test_explicit_column_map(
        self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path
    ):
        result = loader.ingest(
            spectrum_csv,
            tmp_path / "out",
            product="spectrum",
            name="Mapped spectrum",
            description="Spectrum with explicit column mapping",
            timestamp="2026-02-25T12:00:00+00:00",
            column_map={"counts": "counts", "energy": "energy"},
        )
        with h5py.File(result, "r") as f:
            assert "counts" in f
            assert "axes" in f

    def test_auto_detect_columns(
        self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path
    ):
        """When column_map is None, loader auto-detects columns from headers."""
        result = loader.ingest(
            spectrum_csv,
            tmp_path / "out",
            product="spectrum",
            name="Auto spectrum",
            description="Spectrum with auto-detected columns",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            assert "counts" in f


# ---------------------------------------------------------------------------
# Comment-line metadata extraction
# ---------------------------------------------------------------------------


class TestCommentMetadata:
    """Extract metadata from CSV comment lines."""

    def test_metadata_extracted(
        self, loader: CsvLoader, comment_metadata_csv: Path, tmp_path: Path
    ):
        result = loader.ingest(
            comment_metadata_csv,
            tmp_path / "out",
            product="spectrum",
            name="Annotated spectrum",
            description="Spectrum with comment metadata",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            assert "metadata" in f
            meta = f["metadata"]
            assert meta.attrs["units"] == "keV"
            assert meta.attrs["detector"] == "HPGe"
            assert meta.attrs["facility"] == "PSI"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class TestProvenance:
    """Provenance records source CSV SHA-256."""

    def test_provenance_original_files(
        self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path
    ):
        result = loader.ingest(
            spectrum_csv,
            tmp_path / "out",
            product="spectrum",
            name="Provenance test",
            description="Testing provenance recording",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            assert "provenance" in f
            assert "original_files" in f["provenance"]
            orig = f["provenance/original_files"]
            assert orig.shape[0] >= 1
            rec = orig[0]
            sha = rec["sha256"]
            if isinstance(sha, bytes):
                sha = sha.decode()
            assert sha.startswith("sha256:")

    def test_provenance_sha256_correct(
        self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path
    ):
        expected_hash = hashlib.sha256(spectrum_csv.read_bytes()).hexdigest()
        result = loader.ingest(
            spectrum_csv,
            tmp_path / "out",
            product="spectrum",
            name="SHA test",
            description="Verify SHA-256 hash",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            rec = f["provenance/original_files"][0]
            sha = rec["sha256"]
            if isinstance(sha, bytes):
                sha = sha.decode()
            assert sha == f"sha256:{expected_hash}"

    def test_provenance_ingest_group(
        self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path
    ):
        result = loader.ingest(
            spectrum_csv,
            tmp_path / "out",
            product="spectrum",
            name="Ingest prov",
            description="Testing ingest provenance",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            assert "provenance/ingest" in f
            ingest = f["provenance/ingest"]
            assert "tool" in ingest.attrs


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty data, missing file, custom delimiter/comment."""

    def test_nonexistent_file_raises(self, loader: CsvLoader, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            loader.ingest(
                tmp_path / "no_such_file.csv",
                tmp_path / "out",
                product="spectrum",
                name="Missing",
                description="Missing file",
                timestamp="2026-02-25T12:00:00+00:00",
            )

    def test_empty_csv_raises(
        self, loader: CsvLoader, empty_data_csv: Path, tmp_path: Path
    ):
        with pytest.raises(ValueError, match="[Nn]o data"):
            loader.ingest(
                empty_data_csv,
                tmp_path / "out",
                product="spectrum",
                name="Empty",
                description="Empty data",
                timestamp="2026-02-25T12:00:00+00:00",
            )

    def test_custom_comment_char(self, loader: CsvLoader, tmp_path: Path):
        csv_file = tmp_path / "custom_comment.csv"
        csv_file.write_text("% units: MeV\nenergy,counts\n100.0,10\n200.0,20\n")
        result = loader.ingest(
            csv_file,
            tmp_path / "out",
            product="spectrum",
            name="Custom comment",
            description="CSV with % comments",
            timestamp="2026-02-25T12:00:00+00:00",
            comment="%",
        )
        with h5py.File(result, "r") as f:
            assert "metadata" in f
            assert f["metadata"].attrs["units"] == "MeV"

    def test_custom_header_row(self, loader: CsvLoader, tmp_path: Path):
        csv_file = tmp_path / "header_row.csv"
        csv_file.write_text("This is a title line\nenergy,counts\n100.0,10\n200.0,20\n")
        result = loader.ingest(
            csv_file,
            tmp_path / "out",
            product="spectrum",
            name="Header offset",
            description="CSV with header on row 1",
            timestamp="2026-02-25T12:00:00+00:00",
            header_row=1,
        )
        with h5py.File(result, "r") as f:
            assert "counts" in f
            counts = f["counts"][:]
            assert counts.shape == (2,)

    def test_string_source_path(
        self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path
    ):
        """Source can be a str, not just Path."""
        result = loader.ingest(
            str(spectrum_csv),
            tmp_path / "out",
            product="spectrum",
            name="String path",
            description="Source as str",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        assert result.exists()


# ---------------------------------------------------------------------------
# Generic product type
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Calling ingest twice with identical inputs produces two valid, independently sealed files."""

    def test_deterministic(self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path):
        kwargs = dict(
            product="spectrum",
            name="idem-spectrum",
            description="Idempotency test",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        r1 = loader.ingest(spectrum_csv, tmp_path / "a", **kwargs)
        r2 = loader.ingest(spectrum_csv, tmp_path / "b", **kwargs)

        assert r1.exists() and r2.exists()
        assert r1.suffix == ".h5" and r2.suffix == ".h5"
        with h5py.File(r1, "r") as f1, h5py.File(r2, "r") as f2:
            assert f1.attrs["id"] == f2.attrs["id"]
            assert "content_hash" in f1.attrs
            assert "content_hash" in f2.attrs
            np.testing.assert_array_equal(f1["counts"][:], f2["counts"][:])


class TestGenericProduct:
    """Generic product: user specifies product type + column mapping."""

    def test_generic_ingest(self, loader: CsvLoader, tmp_path: Path):
        csv_file = tmp_path / "generic.csv"
        csv_file.write_text("x,y,z\n1.0,2.0,3.0\n4.0,5.0,6.0\n")
        result = loader.ingest(
            csv_file,
            tmp_path / "out",
            product="spectrum",
            name="Generic CSV",
            description="Generic columnar data",
            timestamp="2026-02-25T12:00:00+00:00",
            column_map={"counts": "y", "energy": "x"},
        )
        with h5py.File(result, "r") as f:
            assert "counts" in f
            counts = f["counts"][:]
            np.testing.assert_array_almost_equal(counts, [2.0, 5.0])


class TestFd5Validate:
    """Smoke test: fd5.schema.validate() on CsvLoader output."""

    def test_spectrum_passes_validate(
        self, loader: CsvLoader, spectrum_csv: Path, tmp_path: Path
    ):
        from fd5.schema import validate

        result = loader.ingest(
            spectrum_csv,
            tmp_path / "out",
            product="spectrum",
            name="Validate spectrum",
            description="Validate smoke test",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        errors = validate(result)
        assert errors == [], [e.message for e in errors]
