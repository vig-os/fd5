"""Tests for fd5.ingest.raw module."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

from fd5.imaging.recon import ReconSchema
from fd5.imaging.sinogram import SinogramSchema
from fd5.registry import register_schema


@pytest.fixture(autouse=True)
def _register_schemas():
    register_schema("recon", ReconSchema())
    register_schema("sinogram", SinogramSchema())


def _recon_data(shape: tuple[int, ...] = (8, 16, 16)) -> dict[str, Any]:
    return {
        "volume": np.random.default_rng(42).random(shape, dtype=np.float32),
        "affine": np.eye(4, dtype=np.float64),
        "dimension_order": "ZYX",
        "reference_frame": "LPS",
        "description": "Test recon volume",
    }


def _sinogram_data() -> dict[str, Any]:
    n_planes, n_angular, n_radial = 5, 12, 16
    return {
        "sinogram": np.random.default_rng(7).random(
            (n_planes, n_angular, n_radial), dtype=np.float32
        ),
        "n_radial": n_radial,
        "n_angular": n_angular,
        "n_planes": n_planes,
        "span": 3,
        "max_ring_diff": 2,
        "tof_bins": 0,
    }


class TestIngestArray:
    """Tests for ingest_array()."""

    def test_produces_sealed_recon_file(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_array

        result = ingest_array(
            _recon_data(),
            tmp_path,
            product="recon",
            name="test-recon",
            description="A test recon file",
            timestamp="2025-01-01T00:00:00+00:00",
        )

        assert result.exists()
        assert result.suffix == ".h5"
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "recon"
            assert f.attrs["name"] == "test-recon"
            assert "content_hash" in f.attrs
            assert "id" in f.attrs
            assert "_schema" in f.attrs
            assert "volume" in f

    def test_writes_metadata(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_array

        metadata = {"scanner": "test-scanner", "vendor_series_id": "S001"}
        result = ingest_array(
            _recon_data(),
            tmp_path,
            product="recon",
            name="test-meta",
            description="Metadata test",
            timestamp="2025-01-01T00:00:00+00:00",
            metadata=metadata,
        )

        with h5py.File(result, "r") as f:
            assert "metadata" in f
            assert f["metadata"].attrs["scanner"] == "test-scanner"

    def test_writes_sources(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_array

        sources = [
            {
                "name": "src0",
                "id": "abc",
                "product": "raw",
                "file": "source.h5",
                "content_hash": "sha256:deadbeef",
                "role": "input",
                "description": "test source",
            }
        ]
        result = ingest_array(
            _recon_data(),
            tmp_path,
            product="recon",
            name="test-src",
            description="Sources test",
            timestamp="2025-01-01T00:00:00+00:00",
            sources=sources,
        )

        with h5py.File(result, "r") as f:
            assert "sources" in f

    def test_writes_study_metadata(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_array

        study = {
            "study_type": "clinical",
            "license": "CC-BY-4.0",
            "description": "Test study",
        }
        result = ingest_array(
            _recon_data(),
            tmp_path,
            product="recon",
            name="test-study",
            description="Study test",
            timestamp="2025-01-01T00:00:00+00:00",
            study_metadata=study,
        )

        with h5py.File(result, "r") as f:
            assert "study" in f
            assert f["study"].attrs["type"] == "clinical"

    def test_default_timestamp(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_array

        result = ingest_array(
            _recon_data(),
            tmp_path,
            product="recon",
            name="test-ts",
            description="Default timestamp test",
        )

        assert result.exists()
        with h5py.File(result, "r") as f:
            ts = f.attrs["timestamp"]
            assert len(ts) > 0

    def test_unknown_product_raises(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_array

        with pytest.raises(ValueError, match="no-such-product"):
            ingest_array(
                {},
                tmp_path,
                product="no-such-product",
                name="bad",
                description="Should fail",
            )

    def test_sinogram_product(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_array

        result = ingest_array(
            _sinogram_data(),
            tmp_path,
            product="sinogram",
            name="test-sino",
            description="A test sinogram",
            timestamp="2025-01-01T00:00:00+00:00",
        )

        assert result.exists()
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "sinogram"
            assert "sinogram" in f


class TestIngestBinary:
    """Tests for ingest_binary()."""

    def _write_binary(self, path: Path, arr: np.ndarray) -> None:
        arr.tofile(path)

    def test_reads_binary_and_produces_fd5(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_binary

        shape = (8, 16, 16)
        arr = np.random.default_rng(99).random(shape, dtype=np.float32)
        bin_path = tmp_path / "volume.bin"
        self._write_binary(bin_path, arr)

        out_dir = tmp_path / "output"
        result = ingest_binary(
            bin_path,
            out_dir,
            dtype="float32",
            shape=shape,
            product="recon",
            name="test-binary",
            description="Binary ingest test",
            timestamp="2025-01-01T00:00:00+00:00",
            affine=np.eye(4, dtype=np.float64),
            dimension_order="ZYX",
            reference_frame="LPS",
        )

        assert result.exists()
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "recon"
            read_vol = f["volume"][:]
            np.testing.assert_array_almost_equal(read_vol, arr)

    def test_records_provenance_sha256(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_binary

        shape = (4, 8, 8)
        arr = np.ones(shape, dtype=np.float32)
        bin_path = tmp_path / "ones.bin"
        self._write_binary(bin_path, arr)

        out_dir = tmp_path / "output"
        result = ingest_binary(
            bin_path,
            out_dir,
            dtype="float32",
            shape=shape,
            product="recon",
            name="test-prov",
            description="Provenance test",
            timestamp="2025-01-01T00:00:00+00:00",
            affine=np.eye(4, dtype=np.float64),
            dimension_order="ZYX",
            reference_frame="LPS",
        )

        expected_sha = hashlib.sha256(bin_path.read_bytes()).hexdigest()
        with h5py.File(result, "r") as f:
            assert "provenance" in f
            assert "original_files" in f["provenance"]
            rec = f["provenance"]["original_files"][0]
            assert rec["sha256"].decode() == expected_sha

    def test_nonexistent_binary_raises(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_binary

        with pytest.raises(FileNotFoundError):
            ingest_binary(
                tmp_path / "missing.bin",
                tmp_path / "output",
                dtype="float32",
                shape=(4, 4, 4),
                product="recon",
                name="bad",
                description="Should fail",
            )

    def test_shape_mismatch_raises(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_binary

        arr = np.ones((4, 4, 4), dtype=np.float32)
        bin_path = tmp_path / "small.bin"
        self._write_binary(bin_path, arr)

        with pytest.raises(ValueError, match="cannot reshape"):
            ingest_binary(
                bin_path,
                tmp_path / "output",
                dtype="float32",
                shape=(100, 100, 100),
                product="recon",
                name="bad",
                description="Should fail",
            )


class TestIdempotency:
    """Calling ingest twice with identical inputs produces two valid, independently sealed files."""

    def test_ingest_array_deterministic(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_array

        kwargs = dict(
            product="recon",
            name="idem-recon",
            description="Idempotency test",
            timestamp="2025-01-01T00:00:00+00:00",
        )
        r1 = ingest_array(_recon_data(), tmp_path / "a", **kwargs)
        r2 = ingest_array(_recon_data(), tmp_path / "b", **kwargs)

        assert r1.exists() and r2.exists()
        assert r1.suffix == ".h5" and r2.suffix == ".h5"
        with h5py.File(r1, "r") as f1, h5py.File(r2, "r") as f2:
            assert f1.attrs["id"] == f2.attrs["id"]
            assert f1.attrs["content_hash"] == f2.attrs["content_hash"]

    def test_ingest_binary_produces_two_valid_sealed_files(self, tmp_path: Path):
        from fd5.ingest.raw import ingest_binary

        shape = (4, 8, 8)
        arr = np.ones(shape, dtype=np.float32)
        bin_path = tmp_path / "data.bin"
        arr.tofile(bin_path)

        common = dict(
            dtype="float32",
            shape=shape,
            product="recon",
            name="idem-binary",
            description="Idempotency test",
            timestamp="2025-01-01T00:00:00+00:00",
            affine=np.eye(4, dtype=np.float64),
            dimension_order="ZYX",
            reference_frame="LPS",
        )
        r1 = ingest_binary(bin_path, tmp_path / "a", **common)
        r2 = ingest_binary(bin_path, tmp_path / "b", **common)

        assert r1.exists() and r2.exists()
        assert r1.suffix == ".h5" and r2.suffix == ".h5"
        with h5py.File(r1, "r") as f1, h5py.File(r2, "r") as f2:
            assert f1.attrs["id"] == f2.attrs["id"]
            assert "content_hash" in f1.attrs
            assert "content_hash" in f2.attrs
            np.testing.assert_array_equal(f1["volume"][:], f2["volume"][:])


class TestRawLoader:
    """Tests for RawLoader protocol conformance."""

    def test_satisfies_loader_protocol(self):
        from fd5.ingest._base import Loader
        from fd5.ingest.raw import RawLoader

        loader = RawLoader()
        assert isinstance(loader, Loader)

    def test_supported_product_types(self):
        from fd5.ingest.raw import RawLoader

        loader = RawLoader()
        types = loader.supported_product_types
        assert isinstance(types, list)
        assert "recon" in types

    def test_ingest_produces_file(self, tmp_path: Path):
        from fd5.ingest.raw import RawLoader

        data_path = tmp_path / "data.bin"
        arr = np.random.default_rng(1).random((4, 8, 8), dtype=np.float32)
        arr.tofile(data_path)

        out_dir = tmp_path / "output"
        loader = RawLoader()
        result = loader.ingest(
            data_path,
            out_dir,
            product="recon",
            name="loader-test",
            description="RawLoader test",
            timestamp="2025-01-01T00:00:00+00:00",
            dtype="float32",
            shape=(4, 8, 8),
            affine=np.eye(4, dtype=np.float64),
            dimension_order="ZYX",
            reference_frame="LPS",
        )

        assert result.exists()
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "recon"
