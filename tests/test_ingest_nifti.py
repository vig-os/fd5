"""Tests for fd5.ingest.nifti — NIfTI loader producing sealed fd5 recon files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest import mock

import h5py
import nibabel as nib
import numpy as np
import pytest

from fd5.ingest._base import Loader
from fd5.ingest.nifti import NiftiLoader, ingest_nifti


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def nifti_3d(tmp_path: Path) -> Path:
    """Create a synthetic 3D NIfTI-1 file (.nii)."""
    vol = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    affine = np.diag([2.0, 2.0, 2.0, 1.0])
    img = nib.Nifti1Image(vol, affine)
    p = tmp_path / "volume_3d.nii"
    nib.save(img, p)
    return p


@pytest.fixture()
def nifti_4d(tmp_path: Path) -> Path:
    """Create a synthetic 4D NIfTI-1 file (.nii)."""
    vol = np.arange(48, dtype=np.float32).reshape(2, 2, 3, 4)
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    img = nib.Nifti1Image(vol, affine)
    p = tmp_path / "volume_4d.nii"
    nib.save(img, p)
    return p


@pytest.fixture()
def nifti_gz(tmp_path: Path) -> Path:
    """Create a synthetic 3D NIfTI-1 file (.nii.gz)."""
    vol = np.ones((3, 4, 5), dtype=np.float32)
    affine = np.eye(4)
    img = nib.Nifti1Image(vol, affine)
    p = tmp_path / "compressed.nii.gz"
    nib.save(img, p)
    return p


@pytest.fixture()
def nifti2_3d(tmp_path: Path) -> Path:
    """Create a synthetic 3D NIfTI-2 file."""
    vol = np.ones((3, 4, 5), dtype=np.float32)
    affine = np.eye(4)
    img = nib.Nifti2Image(vol, affine)
    p = tmp_path / "volume_nifti2.nii"
    nib.save(img, p)
    return p


# ---------------------------------------------------------------------------
# Loader protocol conformance
# ---------------------------------------------------------------------------


class TestNiftiLoaderProtocol:
    def test_implements_loader(self):
        loader = NiftiLoader()
        assert isinstance(loader, Loader)

    def test_supported_product_types(self):
        loader = NiftiLoader()
        assert "recon" in loader.supported_product_types


# ---------------------------------------------------------------------------
# ingest_nifti — happy paths
# ---------------------------------------------------------------------------


class TestIngestNifti3D:
    def test_returns_path(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="test-vol",
            description="A test volume",
        )
        assert isinstance(result, Path)
        assert result.exists()
        assert result.suffix == ".h5"

    def test_fd5_root_attrs(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="test-vol",
            description="A test volume",
        )
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "recon"
            assert f.attrs["name"] == "test-vol"
            assert f.attrs["description"] == "A test volume"
            assert "timestamp" in f.attrs
            assert "id" in f.attrs
            assert "content_hash" in f.attrs

    def test_volume_dataset(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="test-vol",
            description="A test volume",
        )
        with h5py.File(result, "r") as f:
            assert "volume" in f
            vol = f["volume"][:]
            assert vol.shape == (2, 3, 4)
            np.testing.assert_allclose(vol, np.arange(24).reshape(2, 3, 4))

    def test_affine_from_sform(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="test-vol",
            description="A test volume",
        )
        with h5py.File(result, "r") as f:
            affine = f["volume"].attrs["affine"]
            expected = np.diag([2.0, 2.0, 2.0, 1.0])
            np.testing.assert_allclose(affine, expected)

    def test_dimension_order_3d(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="test-vol",
            description="A test volume",
        )
        with h5py.File(result, "r") as f:
            dim_order = f["volume"].attrs["dimension_order"]
            assert dim_order == "ZYX"

    def test_reference_frame_default(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="test-vol",
            description="A test volume",
        )
        with h5py.File(result, "r") as f:
            assert f["volume"].attrs["reference_frame"] == "RAS"

    def test_reference_frame_custom(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="test-vol",
            description="A test volume",
            reference_frame="LPS",
        )
        with h5py.File(result, "r") as f:
            assert f["volume"].attrs["reference_frame"] == "LPS"


# ---------------------------------------------------------------------------
# 4D support
# ---------------------------------------------------------------------------


class TestIngestNifti4D:
    def test_4d_volume_shape(self, nifti_4d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_4d,
            out,
            name="dynamic",
            description="4D test",
        )
        with h5py.File(result, "r") as f:
            assert f["volume"][:].shape == (2, 2, 3, 4)

    def test_4d_dimension_order(self, nifti_4d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_4d,
            out,
            name="dynamic",
            description="4D test",
        )
        with h5py.File(result, "r") as f:
            assert f["volume"].attrs["dimension_order"] == "TZYX"


# ---------------------------------------------------------------------------
# Compressed (.nii.gz)
# ---------------------------------------------------------------------------


class TestIngestNiftiGz:
    def test_compressed_file(self, nifti_gz: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_gz,
            out,
            name="compressed",
            description="gzip test",
        )
        with h5py.File(result, "r") as f:
            assert f["volume"][:].shape == (3, 4, 5)


# ---------------------------------------------------------------------------
# NIfTI-2 support
# ---------------------------------------------------------------------------


class TestIngestNifti2:
    def test_nifti2_file(self, nifti2_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti2_3d,
            out,
            name="nifti2-vol",
            description="NIfTI-2 test",
        )
        with h5py.File(result, "r") as f:
            assert f["volume"][:].shape == (3, 4, 5)


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_provenance_original_files(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="prov-test",
            description="Provenance test",
        )
        with h5py.File(result, "r") as f:
            assert "provenance" in f
            assert "original_files" in f["provenance"]
            rec = f["provenance/original_files"][0]
            assert str(nifti_3d) in rec["path"].decode()
            sha = f"sha256:{hashlib.sha256(nifti_3d.read_bytes()).hexdigest()}"
            assert rec["sha256"].decode() == sha

    def test_provenance_ingest_group(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="prov-test",
            description="Provenance test",
        )
        with h5py.File(result, "r") as f:
            assert "provenance/ingest" in f
            ingest_grp = f["provenance/ingest"]
            assert "tool" in ingest_grp.attrs or "tool" in ingest_grp


# ---------------------------------------------------------------------------
# Study metadata
# ---------------------------------------------------------------------------


class TestStudyMetadata:
    def test_study_group_written(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="study-test",
            description="Study test",
            study_metadata={
                "study_type": "phantom",
                "license": "CC-BY-4.0",
                "description": "Phantom study",
            },
        )
        with h5py.File(result, "r") as f:
            assert "study" in f
            assert f["study"].attrs["type"] == "phantom"


# ---------------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------------


class TestTimestamp:
    def test_custom_timestamp(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        ts = "2025-01-15T10:30:00Z"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="ts-test",
            description="Timestamp test",
            timestamp=ts,
        )
        with h5py.File(result, "r") as f:
            assert f.attrs["timestamp"] == ts

    def test_auto_timestamp(self, nifti_3d: Path, tmp_path: Path):
        out = tmp_path / "out"
        result = ingest_nifti(
            nifti_3d,
            out,
            name="ts-test",
            description="Timestamp test",
        )
        with h5py.File(result, "r") as f:
            assert len(f.attrs["timestamp"]) > 0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrors:
    def test_nonexistent_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            ingest_nifti(
                tmp_path / "missing.nii",
                tmp_path / "out",
                name="err",
                description="err",
            )

    def test_invalid_file(self, tmp_path: Path):
        bad = tmp_path / "bad.nii"
        bad.write_bytes(b"not a nifti file")
        with pytest.raises(Exception):
            ingest_nifti(
                bad,
                tmp_path / "out",
                name="err",
                description="err",
            )


# ---------------------------------------------------------------------------
# NiftiLoader.ingest method
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Calling ingest twice with identical inputs produces two valid, independently sealed files."""

    def test_deterministic(self, nifti_3d: Path, tmp_path: Path):
        kwargs = dict(
            name="idem-vol",
            description="Idempotency test",
            timestamp="2025-01-15T10:30:00Z",
        )
        r1 = ingest_nifti(nifti_3d, tmp_path / "a", **kwargs)
        r2 = ingest_nifti(nifti_3d, tmp_path / "b", **kwargs)

        assert r1.exists() and r2.exists()
        assert r1.suffix == ".h5" and r2.suffix == ".h5"
        with h5py.File(r1, "r") as f1, h5py.File(r2, "r") as f2:
            assert f1.attrs["id"] == f2.attrs["id"]
            assert "content_hash" in f1.attrs
            assert "content_hash" in f2.attrs
            np.testing.assert_array_equal(f1["volume"][:], f2["volume"][:])


class TestNiftiLoaderIngest:
    def test_ingest_method(self, nifti_3d: Path, tmp_path: Path):
        loader = NiftiLoader()
        result = loader.ingest(
            nifti_3d,
            tmp_path / "out",
            product="recon",
            name="loader-test",
            description="Via loader",
        )
        assert result.exists()
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "recon"


# ---------------------------------------------------------------------------
# ImportError when nibabel missing
# ---------------------------------------------------------------------------


class TestNibabelImportError:
    def test_clear_message_when_nibabel_missing(self):
        with mock.patch.dict("sys.modules", {"nibabel": None}):
            with pytest.raises(ImportError, match="nibabel"):
                import importlib

                import fd5.ingest.nifti as mod

                importlib.reload(mod)


class TestFd5Validate:
    """Smoke test: fd5.schema.validate() on ingest_nifti output."""

    def test_nifti_passes_validate(self, nifti_3d: Path, tmp_path: Path):
        from fd5.schema import validate

        result = ingest_nifti(
            nifti_3d,
            tmp_path / "out",
            name="validate-nifti",
            description="Validate smoke test",
        )
        errors = validate(result)
        assert errors == [], [e.message for e in errors]
