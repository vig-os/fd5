"""Tests for fd5.naming module."""

from datetime import datetime, timezone


from fd5.naming import generate_filename


class TestGenerateFilename:
    """Tests for generate_filename."""

    def test_full_filename_with_timestamp(self):
        ts = datetime(2024, 7, 24, 18, 14, 0, tzinfo=timezone.utc)
        result = generate_filename(
            product="recon",
            id_hash="sha256:87f032f6abcdef1234567890",
            timestamp=ts,
            descriptors=["ct", "thorax", "dlir"],
        )
        assert result == "2024-07-24_18-14-00_recon-87f032f6_ct_thorax_dlir.h5"

    def test_id_hash_truncated_to_8_hex_chars(self):
        ts = datetime(2025, 3, 15, 9, 22, 0, tzinfo=timezone.utc)
        result = generate_filename(
            product="alignment",
            id_hash="sha256:c4f2a1b8deadbeef",
            timestamp=ts,
            descriptors=["wgs", "sample01", "bwamem2"],
        )
        assert (
            result == "2025-03-15_09-22-00_alignment-c4f2a1b8_wgs_sample01_bwamem2.h5"
        )

    def test_no_timestamp_omits_datetime_prefix(self):
        result = generate_filename(
            product="sim",
            id_hash="sha256:xyz99999aabbccdd",
            timestamp=None,
            descriptors=["pet", "nema", "gate"],
        )
        assert result == "sim-xyz99999_pet_nema_gate.h5"

    def test_single_descriptor(self):
        ts = datetime(2024, 7, 24, 19, 6, 10, tzinfo=timezone.utc)
        result = generate_filename(
            product="listmode",
            id_hash="sha256:def67890aabb1122",
            timestamp=ts,
            descriptors=["coinc"],
        )
        assert result == "2024-07-24_19-06-10_listmode-def67890_coinc.h5"

    def test_empty_descriptors(self):
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = generate_filename(
            product="recon",
            id_hash="sha256:aabbccdd11223344",
            timestamp=ts,
            descriptors=[],
        )
        assert result == "2024-01-01_00-00-00_recon-aabbccdd.h5"

    def test_calibration_no_timestamp(self):
        result = generate_filename(
            product="calibration",
            id_hash="sha256:11223344aabbccdd",
            timestamp=None,
            descriptors=["detector", "energy", "hpge"],
        )
        assert result == "calibration-11223344_detector_energy_hpge.h5"

    def test_id_hash_without_prefix(self):
        ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = generate_filename(
            product="features",
            id_hash="a1b2c3d4e5f6a7b8",
            timestamp=ts,
            descriptors=["satellite", "band4", "ndvi"],
        )
        assert result == "2025-06-01_12-00-00_features-a1b2c3d4_satellite_band4_ndvi.h5"

    def test_return_type_is_str(self):
        result = generate_filename(
            product="recon",
            id_hash="sha256:aabbccdd",
            timestamp=None,
            descriptors=[],
        )
        assert isinstance(result, str)

    def test_extension_is_h5(self):
        result = generate_filename(
            product="recon",
            id_hash="sha256:aabbccdd",
            timestamp=None,
            descriptors=["x"],
        )
        assert result.endswith(".h5")
