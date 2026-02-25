"""Tests for fd5.ingest.parquet — Parquet columnar data loader."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from fd5.ingest._base import Loader
from fd5.ingest.parquet import ParquetLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_parquet(
    path: Path,
    columns: dict[str, list[Any]],
    *,
    metadata: dict[str, str] | None = None,
) -> Path:
    """Write a Parquet file from column data with optional key-value metadata."""
    arrays = {}
    for name, values in columns.items():
        arrays[name] = pa.array(values)
    table = pa.table(arrays)
    if metadata:
        existing = table.schema.metadata or {}
        merged = {**existing, **{k.encode(): v.encode() for k, v in metadata.items()}}
        table = table.replace_schema_metadata(merged)
    pq.write_table(table, path)
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def loader() -> ParquetLoader:
    return ParquetLoader()


@pytest.fixture()
def spectrum_parquet(tmp_path: Path) -> Path:
    """Parquet with energy + counts columns."""
    return _write_parquet(
        tmp_path / "spectrum.parquet",
        {"energy": [100.0, 200.0, 300.0, 400.0], "counts": [10.0, 25.0, 18.0, 7.0]},
        metadata={"units": "keV", "detector": "HPGe"},
    )


@pytest.fixture()
def listmode_parquet(tmp_path: Path) -> Path:
    """Parquet with event-level fields: time, energy, detector_id."""
    return _write_parquet(
        tmp_path / "listmode.parquet",
        {
            "time": [0.001, 0.002, 0.005, 0.010],
            "energy": [511.0, 511.0, 1274.5, 511.0],
            "detector_id": [1, 2, 1, 3],
        },
    )


@pytest.fixture()
def device_data_parquet(tmp_path: Path) -> Path:
    """Parquet with timestamp + sensor channels."""
    return _write_parquet(
        tmp_path / "device.parquet",
        {
            "timestamp": [0.0, 1.0, 2.0],
            "temperature": [22.5, 22.6, 22.4],
            "pressure": [101.3, 101.2, 101.4],
        },
        metadata={"units": "celsius"},
    )


@pytest.fixture()
def generic_parquet(tmp_path: Path) -> Path:
    """Parquet with arbitrary columns."""
    return _write_parquet(
        tmp_path / "generic.parquet",
        {"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0], "z": [7.0, 8.0, 9.0]},
    )


@pytest.fixture()
def metadata_parquet(tmp_path: Path) -> Path:
    """Parquet with rich key-value footer metadata."""
    return _write_parquet(
        tmp_path / "metadata.parquet",
        {"energy": [100.0, 200.0], "counts": [50.0, 75.0]},
        metadata={
            "units": "keV",
            "detector": "HPGe",
            "facility": "PSI",
            "measurement_id": "M-2026-001",
        },
    )


@pytest.fixture()
def int_columns_parquet(tmp_path: Path) -> Path:
    """Parquet with integer-typed columns (schema extraction test)."""
    return _write_parquet(
        tmp_path / "int_cols.parquet",
        {"channel": [1, 2, 3, 4], "counts": [100, 250, 50, 10]},
    )


# ---------------------------------------------------------------------------
# Loader protocol conformance
# ---------------------------------------------------------------------------


class TestParquetLoaderProtocol:
    """ParquetLoader satisfies the Loader protocol."""

    def test_is_loader_instance(self, loader: ParquetLoader):
        assert isinstance(loader, Loader)

    def test_supported_product_types(self, loader: ParquetLoader):
        types = loader.supported_product_types
        assert isinstance(types, list)
        assert "spectrum" in types
        assert "listmode" in types
        assert "device_data" in types

    def test_has_ingest_method(self, loader: ParquetLoader):
        assert callable(getattr(loader, "ingest", None))


# ---------------------------------------------------------------------------
# Spectrum ingest — happy path
# ---------------------------------------------------------------------------


class TestIngestSpectrum:
    """Ingest spectrum Parquet produces valid fd5 file."""

    def test_returns_path(
        self, loader: ParquetLoader, spectrum_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            spectrum_parquet,
            tmp_path / "out",
            product="spectrum",
            name="Test spectrum",
            description="A test spectrum from Parquet",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        assert isinstance(result, Path)
        assert result.exists()
        assert result.suffix == ".h5"

    def test_root_attrs(
        self, loader: ParquetLoader, spectrum_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            spectrum_parquet,
            tmp_path / "out",
            product="spectrum",
            name="Test spectrum",
            description="A test spectrum from Parquet",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "spectrum"
            assert f.attrs["name"] == "Test spectrum"
            assert f.attrs["description"] == "A test spectrum from Parquet"

    def test_data_written(
        self, loader: ParquetLoader, spectrum_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            spectrum_parquet,
            tmp_path / "out",
            product="spectrum",
            name="Test spectrum",
            description="A test spectrum from Parquet",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            assert "counts" in f
            counts = f["counts"][:]
            assert counts.shape == (4,)
            np.testing.assert_array_almost_equal(counts, [10, 25, 18, 7])


# ---------------------------------------------------------------------------
# Listmode ingest
# ---------------------------------------------------------------------------


class TestIngestListmode:
    """Ingest listmode Parquet produces valid fd5 file."""

    def test_returns_path(
        self, loader: ParquetLoader, listmode_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            listmode_parquet,
            tmp_path / "out",
            product="listmode",
            name="Test listmode",
            description="Listmode events from Parquet",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        assert isinstance(result, Path)
        assert result.exists()

    def test_event_data(
        self, loader: ParquetLoader, listmode_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            listmode_parquet,
            tmp_path / "out",
            product="listmode",
            name="Test listmode",
            description="Listmode events from Parquet",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "listmode"
            assert "raw_data" in f
            assert "time" in f["raw_data"]
            assert "energy" in f["raw_data"]
            assert "detector_id" in f["raw_data"]


# ---------------------------------------------------------------------------
# Device data ingest
# ---------------------------------------------------------------------------


class TestIngestDeviceData:
    """Ingest device_data Parquet produces valid fd5 file."""

    def test_returns_path(
        self, loader: ParquetLoader, device_data_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            device_data_parquet,
            tmp_path / "out",
            product="device_data",
            name="Temp log",
            description="Temperature logger data",
            timestamp="2026-02-25T12:00:00+00:00",
            device_type="environmental_sensor",
            device_model="TempSensor-100",
        )
        assert isinstance(result, Path)
        assert result.exists()

    def test_device_data_attrs(
        self, loader: ParquetLoader, device_data_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            device_data_parquet,
            tmp_path / "out",
            product="device_data",
            name="Temp log",
            description="Temperature logger data",
            timestamp="2026-02-25T12:00:00+00:00",
            device_type="environmental_sensor",
            device_model="TempSensor-100",
        )
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "device_data"


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------


class TestColumnMapping:
    """Column mapping configurable via column_map parameter."""

    def test_explicit_column_map(
        self, loader: ParquetLoader, generic_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            generic_parquet,
            tmp_path / "out",
            product="spectrum",
            name="Mapped spectrum",
            description="Spectrum with explicit column mapping",
            timestamp="2026-02-25T12:00:00+00:00",
            column_map={"counts": "y", "energy": "x"},
        )
        with h5py.File(result, "r") as f:
            assert "counts" in f
            counts = f["counts"][:]
            np.testing.assert_array_almost_equal(counts, [4.0, 5.0, 6.0])


# ---------------------------------------------------------------------------
# Parquet schema metadata preserved as fd5 attrs
# ---------------------------------------------------------------------------


class TestParquetMetadata:
    """Parquet key-value footer metadata mapped to fd5 attrs."""

    def test_metadata_preserved(
        self, loader: ParquetLoader, metadata_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            metadata_parquet,
            tmp_path / "out",
            product="spectrum",
            name="Metadata test",
            description="Testing Parquet metadata extraction",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        with h5py.File(result, "r") as f:
            assert "metadata" in f
            meta = f["metadata"]
            assert meta.attrs["units"] == "keV"
            assert meta.attrs["detector"] == "HPGe"
            assert meta.attrs["facility"] == "PSI"

    def test_schema_types_extracted(
        self, loader: ParquetLoader, int_columns_parquet: Path, tmp_path: Path
    ):
        """Parquet column types are used (int columns stay numeric)."""
        result = loader.ingest(
            int_columns_parquet,
            tmp_path / "out",
            product="spectrum",
            name="Int columns",
            description="Integer column types",
            timestamp="2026-02-25T12:00:00+00:00",
            column_map={"counts": "counts", "energy": "channel"},
        )
        with h5py.File(result, "r") as f:
            assert "counts" in f
            counts = f["counts"][:]
            np.testing.assert_array_almost_equal(counts, [100, 250, 50, 10])


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class TestProvenance:
    """Provenance records source Parquet SHA-256."""

    def test_provenance_original_files(
        self, loader: ParquetLoader, spectrum_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            spectrum_parquet,
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
        self, loader: ParquetLoader, spectrum_parquet: Path, tmp_path: Path
    ):
        expected_hash = hashlib.sha256(spectrum_parquet.read_bytes()).hexdigest()
        result = loader.ingest(
            spectrum_parquet,
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
        self, loader: ParquetLoader, spectrum_parquet: Path, tmp_path: Path
    ):
        result = loader.ingest(
            spectrum_parquet,
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


class TestIdempotency:
    """Calling ingest twice with identical inputs produces two valid, independently sealed files."""

    def test_deterministic(
        self, loader: ParquetLoader, spectrum_parquet: Path, tmp_path: Path
    ):
        kwargs = dict(
            product="spectrum",
            name="idem-spectrum",
            description="Idempotency test",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        r1 = loader.ingest(spectrum_parquet, tmp_path / "a", **kwargs)
        r2 = loader.ingest(spectrum_parquet, tmp_path / "b", **kwargs)

        assert r1.exists() and r2.exists()
        assert r1.suffix == ".h5" and r2.suffix == ".h5"
        with h5py.File(r1, "r") as f1, h5py.File(r2, "r") as f2:
            assert f1.attrs["id"] == f2.attrs["id"]
            assert "content_hash" in f1.attrs
            assert "content_hash" in f2.attrs
            np.testing.assert_array_equal(f1["counts"][:], f2["counts"][:])


class TestEdgeCases:
    """Edge cases: missing file, empty table, string source path."""

    def test_nonexistent_file_raises(self, loader: ParquetLoader, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            loader.ingest(
                tmp_path / "no_such_file.parquet",
                tmp_path / "out",
                product="spectrum",
                name="Missing",
                description="Missing file",
                timestamp="2026-02-25T12:00:00+00:00",
            )

    def test_empty_table_raises(self, loader: ParquetLoader, tmp_path: Path):
        empty_path = tmp_path / "empty.parquet"
        table = pa.table({"energy": pa.array([], type=pa.float64())})
        pq.write_table(table, empty_path)
        with pytest.raises(ValueError, match="[Nn]o data"):
            loader.ingest(
                empty_path,
                tmp_path / "out",
                product="spectrum",
                name="Empty",
                description="Empty data",
                timestamp="2026-02-25T12:00:00+00:00",
            )

    def test_string_source_path(
        self, loader: ParquetLoader, spectrum_parquet: Path, tmp_path: Path
    ):
        """Source can be a str, not just Path."""
        result = loader.ingest(
            str(spectrum_parquet),
            tmp_path / "out",
            product="spectrum",
            name="String path",
            description="Source as str",
            timestamp="2026-02-25T12:00:00+00:00",
        )
        assert result.exists()


# ---------------------------------------------------------------------------
# ImportError guard
# ---------------------------------------------------------------------------


class TestImportGuard:
    """Clear ImportError when pyarrow not installed."""

    def test_module_docstring_mentions_pyarrow(self):
        import fd5.ingest.parquet as mod

        assert (
            "pyarrow" in (mod.__doc__ or "").lower()
            or "parquet" in (mod.__doc__ or "").lower()
        )
