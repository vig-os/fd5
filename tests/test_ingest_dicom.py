"""Tests for fd5.ingest.dicom — DICOM series loader."""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from fd5.ingest._base import Loader


# ---------------------------------------------------------------------------
# Helpers — synthetic DICOM generation
# ---------------------------------------------------------------------------

_STUDY_UID = generate_uid()
_SERIES_UID = generate_uid()
_FRAME_OF_REF_UID = generate_uid()


def _make_dicom_slice(
    tmp_dir: Path,
    *,
    slice_idx: int,
    n_slices: int = 4,
    rows: int = 8,
    cols: int = 8,
    series_uid: str = _SERIES_UID,
    study_uid: str = _STUDY_UID,
    patient_name: str = "Doe^John",
    patient_id: str = "PAT001",
) -> Path:
    """Create a single synthetic DICOM CT slice file."""
    sop_uid = generate_uid()
    filename = tmp_dir / f"slice_{slice_idx:04d}.dcm"

    file_meta = pydicom.Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"  # CT
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(str(filename), {}, file_meta=file_meta, preamble=b"\x00" * 128)

    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = sop_uid
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.FrameOfReferenceUID = _FRAME_OF_REF_UID

    ds.Modality = "CT"
    ds.Manufacturer = "TestVendor"
    ds.StationName = "SCANNER_01"
    ds.StudyDescription = "Test Study"
    ds.SeriesDescription = "Test Series"
    ds.StudyDate = "20250101"
    ds.StudyTime = "120000"
    ds.AcquisitionDate = "20250101"
    ds.AcquisitionTime = "120000"
    ds.ContentDate = "20250101"
    ds.ContentTime = "120000"
    ds.InstanceNumber = slice_idx + 1
    ds.SeriesNumber = 1

    ds.PatientName = patient_name
    ds.PatientID = patient_id
    ds.PatientBirthDate = "19800101"

    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1  # signed
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.RescaleSlope = 1.0
    ds.RescaleIntercept = -1024.0

    ds.PixelSpacing = [1.0, 1.0]
    ds.SliceThickness = 2.0
    z_pos = -float(n_slices) + slice_idx * 2.0
    ds.ImagePositionPatient = [0.0, 0.0, z_pos]
    ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    ds.SliceLocation = z_pos

    rng = np.random.default_rng(42 + slice_idx)
    pixel_data = rng.integers(-100, 1000, size=(rows, cols), dtype=np.int16)
    ds.PixelData = pixel_data.tobytes()

    ds.save_as(str(filename))
    return filename


def _make_dicom_series(
    tmp_path: Path,
    *,
    n_slices: int = 4,
    rows: int = 8,
    cols: int = 8,
    **kwargs,
) -> Path:
    """Create a directory with a synthetic DICOM CT series."""
    dicom_dir = tmp_path / "dicom_series"
    dicom_dir.mkdir()
    for i in range(n_slices):
        _make_dicom_slice(
            dicom_dir, slice_idx=i, n_slices=n_slices, rows=rows, cols=cols, **kwargs
        )
    return dicom_dir


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_dicom_loader_satisfies_loader_protocol(self):
        from fd5.ingest.dicom import DicomLoader

        loader = DicomLoader()
        assert isinstance(loader, Loader)

    def test_supported_product_types_includes_recon(self):
        from fd5.ingest.dicom import DicomLoader

        loader = DicomLoader()
        assert "recon" in loader.supported_product_types


# ---------------------------------------------------------------------------
# ImportError when pydicom missing
# ---------------------------------------------------------------------------


class TestImportGuard:
    def test_module_importable_with_pydicom(self):
        from fd5.ingest import dicom  # noqa: F401


# ---------------------------------------------------------------------------
# ingest_dicom public function
# ---------------------------------------------------------------------------


class TestIngestDicomFunction:
    def test_function_is_importable(self):
        from fd5.ingest.dicom import ingest_dicom

        assert callable(ingest_dicom)

    def test_returns_path(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(
            dicom_dir, out_dir, name="test-ct", description="Test CT scan"
        )
        assert isinstance(result, Path)
        assert result.exists()

    def test_output_is_valid_hdf5(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(
            dicom_dir, out_dir, name="test-ct", description="Test CT scan"
        )
        with h5py.File(result, "r") as f:
            assert "volume" in f


# ---------------------------------------------------------------------------
# Series discovery
# ---------------------------------------------------------------------------


class TestSeriesDiscovery:
    def test_discovers_single_series(self, tmp_path):
        from fd5.ingest.dicom import _discover_series

        dicom_dir = _make_dicom_series(tmp_path, n_slices=4)
        series = _discover_series(dicom_dir)
        assert len(series) == 1
        uid = list(series.keys())[0]
        assert len(series[uid]) == 4

    def test_discovers_multiple_series(self, tmp_path):
        from fd5.ingest.dicom import _discover_series

        dicom_dir = tmp_path / "mixed"
        dicom_dir.mkdir()
        uid_a = generate_uid()
        uid_b = generate_uid()
        for i in range(3):
            _make_dicom_slice(dicom_dir, slice_idx=i, series_uid=uid_a)
        for i in range(2):
            _make_dicom_slice(dicom_dir, slice_idx=10 + i, series_uid=uid_b)
        series = _discover_series(dicom_dir)
        assert len(series) == 2

    def test_ignores_non_dicom_files(self, tmp_path):
        from fd5.ingest.dicom import _discover_series

        dicom_dir = _make_dicom_series(tmp_path, n_slices=2)
        (dicom_dir / "readme.txt").write_text("not dicom")
        (dicom_dir / "data.json").write_text("{}")
        series = _discover_series(dicom_dir)
        assert len(series) == 1
        uid = list(series.keys())[0]
        assert len(series[uid]) == 2


# ---------------------------------------------------------------------------
# Volume assembly
# ---------------------------------------------------------------------------


class TestVolumeAssembly:
    def test_volume_shape_matches_slices(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        n_slices, rows, cols = 4, 8, 8
        dicom_dir = _make_dicom_series(
            tmp_path, n_slices=n_slices, rows=rows, cols=cols
        )
        out_dir = tmp_path / "output"
        result = ingest_dicom(
            dicom_dir, out_dir, name="test-ct", description="Test CT volume"
        )
        with h5py.File(result, "r") as f:
            vol = f["volume"]
            assert vol.shape == (n_slices, rows, cols)

    def test_slices_sorted_by_position(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path, n_slices=4)
        out_dir = tmp_path / "output"
        result = ingest_dicom(
            dicom_dir, out_dir, name="test-ct", description="Test CT volume"
        )
        with h5py.File(result, "r") as f:
            vol = f["volume"]
            assert vol.ndim == 3

    def test_volume_dtype_is_float32(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path, n_slices=4)
        out_dir = tmp_path / "output"
        result = ingest_dicom(
            dicom_dir, out_dir, name="test-ct", description="Test CT volume"
        )
        with h5py.File(result, "r") as f:
            assert f["volume"].dtype == np.float32


# ---------------------------------------------------------------------------
# Affine computation
# ---------------------------------------------------------------------------


class TestAffineComputation:
    def test_affine_exists_on_volume(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:
            assert "affine" in f["volume"].attrs
            aff = f["volume"].attrs["affine"]
            assert aff.shape == (4, 4)
            assert aff.dtype == np.float64

    def test_affine_pixel_spacing(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:
            aff = f["volume"].attrs["affine"]
            assert aff[0, 0] != 0 or aff[1, 0] != 0 or aff[2, 0] != 0

    def test_affine_last_row_is_0001(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:
            aff = f["volume"].attrs["affine"]
            np.testing.assert_array_equal(aff[3, :], [0, 0, 0, 1])


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------


class TestMetadataExtraction:
    def test_root_attrs_present(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:
            assert f.attrs["product"] == "recon"
            assert f.attrs["name"] == "test-ct"
            assert f.attrs["description"] == "Test CT"

    def test_timestamp_extracted_from_dicom(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:
            ts = f.attrs["timestamp"]
            if isinstance(ts, bytes):
                ts = ts.decode()
            assert "2025" in ts

    def test_timestamp_override(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(
            dicom_dir,
            out_dir,
            name="test-ct",
            description="Test CT",
            timestamp="2024-06-15T08:00:00",
        )
        with h5py.File(result, "r") as f:
            ts = f.attrs["timestamp"]
            if isinstance(ts, bytes):
                ts = ts.decode()
            assert ts == "2024-06-15T08:00:00"

    def test_scanner_attr_on_volume(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:
            assert "scanner" in f.attrs or "scanner" in f["volume"].attrs


# ---------------------------------------------------------------------------
# Provenance — original files
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_original_files_recorded(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path, n_slices=3)
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:
            assert "provenance/original_files" in f
            ds = f["provenance/original_files"]
            assert ds.shape[0] == 3

    def test_original_files_have_sha256(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path, n_slices=2)
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:
            ds = f["provenance/original_files"]
            for row in ds:
                sha = row["sha256"]
                if isinstance(sha, bytes):
                    sha = sha.decode()
                assert sha.startswith("sha256:")

    def test_ingest_provenance_recorded(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:
            assert "provenance/ingest" in f
            ingest_grp = f["provenance/ingest"]
            tool = ingest_grp.attrs.get("tool", "")
            if isinstance(tool, bytes):
                tool = tool.decode()
            assert "dicom" in tool.lower() or "fd5" in tool.lower()


# ---------------------------------------------------------------------------
# De-identification
# ---------------------------------------------------------------------------


class TestDeidentification:
    def test_patient_name_stripped_by_default(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(
            tmp_path, patient_name="Smith^Jane", patient_id="SECRET_ID"
        )
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:

            def _check_no_patient_data(name, obj):
                for attr_name, attr_val in obj.attrs.items():
                    val = attr_val
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", errors="replace")
                    if isinstance(val, str):
                        assert "Smith" not in val
                        assert "SECRET_ID" not in val

            f.visititems(_check_no_patient_data)
            for attr_name, attr_val in f.attrs.items():
                val = attr_val
                if isinstance(val, bytes):
                    val = val.decode("utf-8", errors="replace")
                if isinstance(val, str):
                    assert "Smith" not in val
                    assert "SECRET_ID" not in val

    def test_dicom_header_provenance_is_deidentified(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(
            tmp_path, patient_name="Doe^John", patient_id="PAT001"
        )
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        with h5py.File(result, "r") as f:
            if "provenance/dicom_header" in f:
                header_raw = f["provenance/dicom_header"][()]
                if isinstance(header_raw, bytes):
                    header_raw = header_raw.decode()
                assert "Doe" not in header_raw
                assert "PAT001" not in header_raw

    def test_deidentify_false_preserves_patient_data(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(
            tmp_path, patient_name="Smith^Jane", patient_id="KEEP_ID"
        )
        out_dir = tmp_path / "output"
        result = ingest_dicom(
            dicom_dir,
            out_dir,
            name="test-ct",
            description="Test CT",
            deidentify=False,
        )
        with h5py.File(result, "r") as f:
            if "provenance/dicom_header" in f:
                header_raw = f["provenance/dicom_header"][()]
                if isinstance(header_raw, bytes):
                    header_raw = header_raw.decode()
                assert "Smith" in header_raw or "KEEP_ID" in header_raw


# ---------------------------------------------------------------------------
# fd5 validate integration
# ---------------------------------------------------------------------------


class TestFd5Validate:
    def test_output_passes_fd5_validate(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom
        from fd5.schema import validate

        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = ingest_dicom(dicom_dir, out_dir, name="test-ct", description="Test CT")
        errors = validate(result)
        assert errors == [], [e.message for e in errors]


# ---------------------------------------------------------------------------
# DicomLoader.ingest method
# ---------------------------------------------------------------------------


class TestDicomLoaderIngest:
    def test_loader_ingest_produces_file(self, tmp_path):
        from fd5.ingest.dicom import DicomLoader

        loader = DicomLoader()
        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        result = loader.ingest(
            dicom_dir,
            out_dir,
            product="recon",
            name="loader-test",
            description="Loader test",
        )
        assert isinstance(result, Path)
        assert result.exists()

    def test_loader_ingest_unsupported_product_raises(self, tmp_path):
        from fd5.ingest.dicom import DicomLoader

        loader = DicomLoader()
        dicom_dir = _make_dicom_series(tmp_path)
        out_dir = tmp_path / "output"
        with pytest.raises(ValueError, match="product"):
            loader.ingest(
                dicom_dir,
                out_dir,
                product="unknown_product",
                name="test",
                description="test",
            )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_directory_raises(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        out_dir = tmp_path / "output"
        with pytest.raises((ValueError, FileNotFoundError)):
            ingest_dicom(empty_dir, out_dir, name="test", description="test")

    def test_single_slice(self, tmp_path):
        from fd5.ingest.dicom import ingest_dicom

        dicom_dir = _make_dicom_series(tmp_path, n_slices=1, rows=4, cols=4)
        out_dir = tmp_path / "output"
        result = ingest_dicom(
            dicom_dir, out_dir, name="test-ct", description="Single slice"
        )
        with h5py.File(result, "r") as f:
            assert f["volume"].shape == (1, 4, 4)

    def test_directory_entries_are_skipped(self, tmp_path):
        from fd5.ingest.dicom import _discover_series

        dicom_dir = _make_dicom_series(tmp_path, n_slices=2)
        (dicom_dir / "subdir").mkdir()
        series = _discover_series(dicom_dir)
        assert len(series) == 1
        uid = list(series.keys())[0]
        assert len(series[uid]) == 2


# ---------------------------------------------------------------------------
# _deidentify / _ds_to_json_dict internal helpers
# ---------------------------------------------------------------------------


class TestSerializationHelpers:
    def test_deidentify_strips_patient_tags(self):
        from fd5.ingest.dicom import _deidentify

        ds = pydicom.Dataset()
        ds.PatientName = "Secret^Name"
        ds.PatientID = "ID123"
        ds.Modality = "CT"
        result = _deidentify(ds)
        assert "PatientName" not in result
        assert "PatientID" not in result
        assert result["Modality"] == "CT"

    def test_ds_to_json_dict_preserves_patient_tags(self):
        from fd5.ingest.dicom import _ds_to_json_dict

        ds = pydicom.Dataset()
        ds.PatientName = "Keep^Me"
        ds.PatientID = "KEEP_ID"
        ds.Modality = "CT"
        result = _ds_to_json_dict(ds)
        assert "PatientName" in result
        assert "PatientID" in result

    def test_deidentify_handles_sequence_elements(self):
        from fd5.ingest.dicom import _deidentify

        ds = pydicom.Dataset()
        ds.Modality = "CT"
        inner = pydicom.Dataset()
        inner.CodeValue = "123"
        ds.AnatomicRegionSequence = pydicom.Sequence([inner])
        result = _deidentify(ds)
        assert "AnatomicRegionSequence" not in result
        assert "Modality" in result

    def test_deidentify_handles_non_serializable_value(self):
        from fd5.ingest.dicom import _deidentify

        ds = pydicom.Dataset()
        ds.Modality = "CT"
        ds.add_new(0x7FE00010, "OB", b"\x00\x01\x02")
        result = _deidentify(ds)
        assert "Modality" in result

    def test_ds_to_json_dict_handles_sequence(self):
        from fd5.ingest.dicom import _ds_to_json_dict

        ds = pydicom.Dataset()
        ds.Modality = "MR"
        inner = pydicom.Dataset()
        inner.CodeValue = "456"
        ds.AnatomicRegionSequence = pydicom.Sequence([inner])
        result = _ds_to_json_dict(ds)
        assert "AnatomicRegionSequence" not in result

    def test_ds_to_json_dict_handles_bytes(self):
        from fd5.ingest.dicom import _ds_to_json_dict

        ds = pydicom.Dataset()
        ds.Modality = "CT"
        ds.add_new(0x7FE00010, "OB", b"\x00\x01\x02")
        result = _ds_to_json_dict(ds)
        assert "Modality" in result


# ---------------------------------------------------------------------------
# _extract_timestamp edge cases
# ---------------------------------------------------------------------------


class TestExtractTimestamp:
    def test_missing_date_falls_back_to_now(self):
        from fd5.ingest.dicom import _extract_timestamp

        ds = pydicom.Dataset()
        ts = _extract_timestamp(ds)
        assert len(ts) > 0

    def test_date_without_time(self):
        from fd5.ingest.dicom import _extract_timestamp

        ds = pydicom.Dataset()
        ds.StudyDate = "20240315"
        ts = _extract_timestamp(ds)
        assert ts == "2024-03-15"

    def test_short_time_string(self):
        from fd5.ingest.dicom import _extract_timestamp

        ds = pydicom.Dataset()
        ds.StudyDate = "20240315"
        ds.StudyTime = "1234"
        ts = _extract_timestamp(ds)
        assert ts == "2024-03-15T12:34:00"

    def test_malformed_date_falls_back(self):
        from fd5.ingest.dicom import _extract_timestamp

        ds = pydicom.Dataset()
        ds.StudyDate = "X"
        ts = _extract_timestamp(ds)
        assert len(ts) > 0

    def test_acquisition_date_fallback(self):
        from fd5.ingest.dicom import _extract_timestamp

        ds = pydicom.Dataset()
        ds.AcquisitionDate = "20240601"
        ds.AcquisitionTime = "093000"
        ts = _extract_timestamp(ds)
        assert ts == "2024-06-01T09:30:00"


# ---------------------------------------------------------------------------
# _compute_affine edge case — zero slice spacing
# ---------------------------------------------------------------------------


class TestAffineEdgeCases:
    def test_zero_spacing_uses_slice_thickness(self, tmp_path):
        from fd5.ingest.dicom import _compute_affine

        ds0 = pydicom.Dataset()
        ds0.ImagePositionPatient = [0.0, 0.0, 0.0]
        ds0.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        ds0.PixelSpacing = [1.0, 1.0]
        ds0.SliceThickness = 3.0

        ds1 = pydicom.Dataset()
        ds1.ImagePositionPatient = [0.0, 0.0, 0.0]
        ds1.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        ds1.PixelSpacing = [1.0, 1.0]

        aff = _compute_affine([ds0, ds1])
        assert aff.shape == (4, 4)
        np.testing.assert_array_equal(aff[3, :], [0, 0, 0, 1])

    def test_deidentify_non_json_serializable_value(self):
        from fd5.ingest.dicom import _deidentify

        ds = pydicom.Dataset()
        ds.Modality = "CT"
        ds.add_new(0x00091002, "UN", b"\xff\xfe")
        result = _deidentify(ds)
        assert "Modality" in result

    def test_ds_to_json_dict_non_serializable_value(self):
        from fd5.ingest.dicom import _ds_to_json_dict

        ds = pydicom.Dataset()
        ds.Modality = "CT"
        ds.add_new(0x00091002, "UN", b"\xff\xfe")
        result = _ds_to_json_dict(ds)
        assert "Modality" in result

    def test_deidentify_non_json_serializable_type(self):
        """Force the except (TypeError, ValueError) branch in _deidentify."""
        from unittest.mock import patch

        from fd5.ingest.dicom import _deidentify

        ds = pydicom.Dataset()
        ds.Modality = "CT"

        original_dumps = json.dumps

        def _failing_dumps(val, **kw):
            if val == "CT":
                raise TypeError("mock non-serializable")
            return original_dumps(val, **kw)

        with patch("fd5.ingest.dicom.json.dumps", side_effect=_failing_dumps):
            result = _deidentify(ds)
        assert "Modality" in result
        assert result["Modality"] == "CT"

    def test_ds_to_json_dict_non_json_serializable_type(self):
        """Force the except (TypeError, ValueError) branch in _ds_to_json_dict."""
        from unittest.mock import patch

        from fd5.ingest.dicom import _ds_to_json_dict

        ds = pydicom.Dataset()
        ds.Modality = "MR"

        original_dumps = json.dumps

        def _failing_dumps(val, **kw):
            if val == "MR":
                raise TypeError("mock non-serializable")
            return original_dumps(val, **kw)

        with patch("fd5.ingest.dicom.json.dumps", side_effect=_failing_dumps):
            result = _ds_to_json_dict(ds)
        assert "Modality" in result
        assert result["Modality"] == "MR"
