"""Tests for fd5.naming.generate_filename."""

from datetime import datetime

import pytest

from fd5.naming import generate_filename


class TestHappyPath:
    """Expected inputs produce correctly formatted filenames."""

    def test_full_filename_with_timestamp_and_descriptors(self):
        result = generate_filename(
            product="recon",
            id_hash="sha256:87f032f6abcdef01",
            timestamp=datetime(2024, 7, 24, 18, 14, 0),
            descriptors=["ct", "thorax", "dlir"],
        )
        assert result == "2024-07-24_18-14-00_recon-87f032f6_ct_thorax_dlir.h5"

    def test_no_timestamp_omits_datetime_prefix(self):
        result = generate_filename(
            product="sim",
            id_hash="sha256:xyz99999aabbccdd",
            timestamp=None,
            descriptors=["pet", "nema", "gate"],
        )
        assert result == "sim-xyz99999_pet_nema_gate.h5"

    def test_single_descriptor(self):
        result = generate_filename(
            product="spectrum",
            id_hash="sha256:44556677aabbccdd",
            timestamp=datetime(2024, 7, 24, 19, 30, 0),
            descriptors=["pet"],
        )
        assert result == "2024-07-24_19-30-00_spectrum-44556677_pet.h5"

    def test_no_descriptors(self):
        result = generate_filename(
            product="recon",
            id_hash="sha256:aabbccdd11223344",
            timestamp=datetime(2025, 1, 1, 0, 0, 0),
            descriptors=[],
        )
        assert result == "2025-01-01_00-00-00_recon-aabbccdd.h5"

    def test_no_timestamp_no_descriptors(self):
        result = generate_filename(
            product="calibration",
            id_hash="sha256:11223344aabbccdd",
        )
        assert result == "calibration-11223344.h5"

    def test_defaults_for_optional_params(self):
        result = generate_filename("sim", "sha256:deadbeef12345678")
        assert result == "sim-deadbeef.h5"


class TestIdHashTruncation:
    """id_hash is split on ':' and truncated to 8 hex chars."""

    def test_truncates_long_hash_to_8_chars(self):
        result = generate_filename(
            product="recon",
            id_hash="sha256:2a3ac438e7f1b9d0c6a5",
            timestamp=datetime(2024, 7, 24, 19, 6, 10),
            descriptors=["pet", "qclear", "wb"],
        )
        assert result == "2024-07-24_19-06-10_recon-2a3ac438_pet_qclear_wb.h5"

    def test_hash_exactly_8_chars(self):
        result = generate_filename(
            product="sim",
            id_hash="sha256:abcdef01",
            descriptors=["test"],
        )
        assert result == "sim-abcdef01_test.h5"

    def test_hash_shorter_than_8_chars_used_as_is(self):
        result = generate_filename(
            product="sim",
            id_hash="sha256:abc",
            descriptors=["test"],
        )
        assert result == "sim-abc_test.h5"


class TestTimestampFormatting:
    """Timestamp formatted as YYYY-MM-DD_HH-MM-SS."""

    def test_midnight(self):
        result = generate_filename(
            product="recon",
            id_hash="sha256:aabbccdd",
            timestamp=datetime(2025, 12, 31, 0, 0, 0),
        )
        assert result == "2025-12-31_00-00-00_recon-aabbccdd.h5"

    def test_end_of_day(self):
        result = generate_filename(
            product="recon",
            id_hash="sha256:aabbccdd",
            timestamp=datetime(2025, 12, 31, 23, 59, 59),
        )
        assert result == "2025-12-31_23-59-59_recon-aabbccdd.h5"


class TestEdgeCases:
    """Boundary and unusual inputs."""

    def test_empty_descriptors_tuple(self):
        result = generate_filename(
            product="recon",
            id_hash="sha256:aabbccdd",
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            descriptors=(),
        )
        assert result == "2025-01-01_12-00-00_recon-aabbccdd.h5"

    def test_many_descriptors(self):
        result = generate_filename(
            product="features",
            id_hash="sha256:a1b2c3d4e5f6",
            timestamp=datetime(2025, 6, 1, 12, 0, 0),
            descriptors=["satellite", "band4", "ndvi"],
        )
        assert result == "2025-06-01_12-00-00_features-a1b2c3d4_satellite_band4_ndvi.h5"

    def test_whitepaper_example_calibration_no_timestamp(self):
        result = generate_filename(
            product="calibration",
            id_hash="sha256:11223344aabbccdd",
            descriptors=["detector", "energy", "hpge"],
        )
        assert result == "calibration-11223344_detector_energy_hpge.h5"


class TestInputValidation:
    """Invalid inputs raise appropriate errors."""

    def test_empty_product_raises(self):
        with pytest.raises(ValueError, match="product"):
            generate_filename(product="", id_hash="sha256:aabbccdd")

    def test_id_hash_missing_prefix_raises(self):
        with pytest.raises(ValueError, match="id_hash"):
            generate_filename(product="recon", id_hash="aabbccdd")

    def test_id_hash_empty_hex_after_prefix_raises(self):
        with pytest.raises(ValueError, match="id_hash"):
            generate_filename(product="recon", id_hash="sha256:")


class TestIdempotency:
    """Calling generate_filename twice with the same inputs produces the same result."""

    def test_same_inputs_same_output(self):
        kwargs = dict(
            product="recon",
            id_hash="sha256:87f032f6abcdef01",
            timestamp=datetime(2024, 7, 24, 18, 14, 0),
            descriptors=["ct", "thorax", "dlir"],
        )
        assert generate_filename(**kwargs) == generate_filename(**kwargs)
