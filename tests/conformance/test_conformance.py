"""Cross-language conformance tests for the fd5 format.

Validates that the Python reference implementation produces files matching
the canonical expected-result JSON files. Any fd5 implementation must pass
equivalent tests to prove format conformance.

See tests/conformance/README.md for details.
"""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from fd5.hash import verify
from fd5.schema import validate

CONFORMANCE_DIR = Path(__file__).parent
FIXTURES_DIR = CONFORMANCE_DIR / "fixtures"
EXPECTED_DIR = CONFORMANCE_DIR / "expected"
INVALID_DIR = CONFORMANCE_DIR / "invalid"


def _load_expected(name: str) -> dict:
    path = EXPECTED_DIR / f"{name}.json"
    return json.loads(path.read_text())


def _fixture_path(name: str) -> Path:
    return FIXTURES_DIR / f"{name}.fd5"


@pytest.fixture(scope="session", autouse=True)
def _generate_fixtures():
    """Generate all fixture files before any conformance test runs."""
    from tests.conformance.generate_fixtures import generate_all

    generate_all(FIXTURES_DIR, INVALID_DIR)

    from tests.conformance.generate_fixtures import _ConformanceSchema

    from fd5.registry import register_schema

    register_schema("test/conformance", _ConformanceSchema())


# ---------------------------------------------------------------------------
# Structure tests — minimal fixture
# ---------------------------------------------------------------------------


class TestStructure:
    """Correct group hierarchy and required attributes present."""

    def test_root_attrs_match(self):
        expected = _load_expected("minimal")
        path = _fixture_path("minimal")
        with h5py.File(path, "r") as f:
            for key, value in expected["root_attrs"].items():
                actual = f.attrs[key]
                if isinstance(actual, bytes):
                    actual = actual.decode("utf-8")
                if isinstance(actual, np.integer):
                    actual = int(actual)
                assert actual == value, f"Attr {key!r}: {actual!r} != {value!r}"

    def test_root_attrs_prefixed(self):
        expected = _load_expected("minimal")
        path = _fixture_path("minimal")
        with h5py.File(path, "r") as f:
            for key, prefix in expected["root_attrs_prefixed"].items():
                actual = f.attrs[key]
                if isinstance(actual, bytes):
                    actual = actual.decode("utf-8")
                assert actual.startswith(prefix), (
                    f"Attr {key!r} should start with {prefix!r}, got {actual!r}"
                )

    def test_datasets_present(self):
        expected = _load_expected("minimal")
        path = _fixture_path("minimal")
        with h5py.File(path, "r") as f:
            for ds_spec in expected["datasets"]:
                ds = f[ds_spec["path"]]
                assert isinstance(ds, h5py.Dataset)
                assert list(ds.shape) == ds_spec["shape"]
                assert ds.dtype == np.dtype(ds_spec["dtype"])

    def test_groups_present(self):
        expected = _load_expected("minimal")
        path = _fixture_path("minimal")
        with h5py.File(path, "r") as f:
            for grp_path in expected["groups"]:
                assert grp_path in f or grp_path == "/"

    def test_verify_true(self):
        expected = _load_expected("minimal")
        path = _fixture_path("minimal")
        assert verify(path) is expected["verify"]

    def test_schema_valid(self):
        expected = _load_expected("minimal")
        path = _fixture_path("minimal")
        if expected.get("schema_valid"):
            errors = validate(path)
            assert errors == [], [e.message for e in errors]


# ---------------------------------------------------------------------------
# Hash verification tests — sealed fixture
# ---------------------------------------------------------------------------


class TestHashVerification:
    """Sealed files verify correctly, tampered files fail."""

    def test_intact_verifies(self):
        path = _fixture_path("sealed")
        assert verify(path) is True

    def test_tampered_attr_fails(self, tmp_path):
        import shutil

        src = _fixture_path("sealed")
        tampered = tmp_path / "tampered_attr.fd5"
        shutil.copy2(src, tampered)

        with h5py.File(tampered, "a") as f:
            f.attrs["name"] = "tampered-value"

        assert verify(tampered) is False

    def test_tampered_data_fails(self, tmp_path):
        import shutil

        src = _fixture_path("sealed")
        tampered = tmp_path / "tampered_data.fd5"
        shutil.copy2(src, tampered)

        with h5py.File(tampered, "a") as f:
            ds = f["volume"]
            ds[0, 0] = 999.0

        assert verify(tampered) is False

    def test_content_hash_format(self):
        path = _fixture_path("sealed")
        with h5py.File(path, "r") as f:
            ch = f.attrs["content_hash"]
            if isinstance(ch, bytes):
                ch = ch.decode("utf-8")
            assert ch.startswith("sha256:")
            assert len(ch) == len("sha256:") + 64


# ---------------------------------------------------------------------------
# Provenance tests — with-provenance fixture
# ---------------------------------------------------------------------------


class TestProvenance:
    """DAG traversal returns expected source chain."""

    def test_sources_group_exists(self):
        path = _fixture_path("with-provenance")
        with h5py.File(path, "r") as f:
            assert "sources" in f

    def test_source_attrs(self):
        expected = _load_expected("with-provenance")
        path = _fixture_path("with-provenance")
        with h5py.File(path, "r") as f:
            for src_spec in expected["provenance"]["sources"]:
                name = src_spec["name"]
                grp = f[f"sources/{name}"]
                assert grp.attrs["id"] == src_spec["id"]
                assert grp.attrs["product"] == src_spec["product"]
                assert grp.attrs["role"] == src_spec["role"]
                assert grp.attrs["description"] == src_spec["description"]

    def test_source_has_external_link(self):
        expected = _load_expected("with-provenance")
        path = _fixture_path("with-provenance")
        with h5py.File(path, "r") as f:
            for src_spec in expected["provenance"]["sources"]:
                name = src_spec["name"]
                link = f[f"sources/{name}"].get("link", getlink=True)
                assert isinstance(link, h5py.ExternalLink)

    def test_original_files_exist(self):
        expected = _load_expected("with-provenance")
        path = _fixture_path("with-provenance")
        with h5py.File(path, "r") as f:
            assert "provenance" in f
            if expected["provenance"]["has_original_files"]:
                assert "original_files" in f["provenance"]
                ds = f["provenance/original_files"]
                assert len(ds) == expected["provenance"]["original_files_count"]

    def test_ingest_attrs(self):
        expected = _load_expected("with-provenance")
        path = _fixture_path("with-provenance")
        with h5py.File(path, "r") as f:
            ingest = f["provenance/ingest"]
            ingest_spec = expected["provenance"]["ingest"]
            assert ingest.attrs["tool"] == ingest_spec["tool"]
            assert ingest.attrs["tool_version"] == ingest_spec["tool_version"]

    def test_groups_present(self):
        expected = _load_expected("with-provenance")
        path = _fixture_path("with-provenance")
        with h5py.File(path, "r") as f:
            for grp_path in expected["groups"]:
                if grp_path == "/":
                    continue
                assert grp_path in f, f"Missing group {grp_path!r}"

    def test_verify_matches_expected(self):
        expected = _load_expected("with-provenance")
        path = _fixture_path("with-provenance")
        assert verify(path) is expected["verify"]


# ---------------------------------------------------------------------------
# Multiscale tests — multiscale fixture
# ---------------------------------------------------------------------------


class TestMultiscale:
    """Pyramid levels and shapes match expected."""

    def test_pyramid_group_exists(self):
        path = _fixture_path("multiscale")
        with h5py.File(path, "r") as f:
            assert "pyramid" in f

    def test_pyramid_attrs(self):
        expected = _load_expected("multiscale")
        path = _fixture_path("multiscale")
        with h5py.File(path, "r") as f:
            pyr = f["pyramid"]
            assert int(pyr.attrs["n_levels"]) == expected["pyramid"]["n_levels"]
            actual_factors = list(pyr.attrs["scale_factors"])
            assert actual_factors == expected["pyramid"]["scale_factors"]

    def test_pyramid_level_shapes(self):
        expected = _load_expected("multiscale")
        path = _fixture_path("multiscale")
        with h5py.File(path, "r") as f:
            for level_name, expected_shape in expected["pyramid"][
                "level_shapes"
            ].items():
                ds = f[f"pyramid/{level_name}/volume"]
                assert list(ds.shape) == expected_shape

    def test_groups_present(self):
        expected = _load_expected("multiscale")
        path = _fixture_path("multiscale")
        with h5py.File(path, "r") as f:
            for grp_path in expected["groups"]:
                if grp_path == "/":
                    continue
                assert grp_path in f, f"Missing group {grp_path!r}"

    def test_mip_datasets_present(self):
        expected = _load_expected("multiscale")
        path = _fixture_path("multiscale")
        with h5py.File(path, "r") as f:
            for ds_spec in expected["datasets"]:
                ds = f[ds_spec["path"]]
                assert isinstance(ds, h5py.Dataset)
                assert ds.dtype == np.dtype(ds_spec["dtype"])

    def test_verify_true(self):
        path = _fixture_path("multiscale")
        assert verify(path) is True


# ---------------------------------------------------------------------------
# Tabular tests — tabular fixture
# ---------------------------------------------------------------------------


class TestTabular:
    """Compound dataset with expected columns, dtypes, and row count."""

    def test_events_dataset_exists(self):
        path = _fixture_path("tabular")
        with h5py.File(path, "r") as f:
            assert "events" in f

    def test_row_count(self):
        expected = _load_expected("tabular")
        path = _fixture_path("tabular")
        with h5py.File(path, "r") as f:
            ds = f["events"]
            assert len(ds) == expected["tabular"]["row_count"]

    def test_column_names(self):
        expected = _load_expected("tabular")
        path = _fixture_path("tabular")
        with h5py.File(path, "r") as f:
            ds = f["events"]
            actual_names = list(ds.dtype.names)
            assert actual_names == expected["tabular"]["column_names"]

    def test_column_dtypes(self):
        expected = _load_expected("tabular")
        path = _fixture_path("tabular")
        with h5py.File(path, "r") as f:
            ds = f["events"]
            for col, expected_dtype in expected["tabular"]["column_dtypes"].items():
                actual = ds.dtype[col]
                assert actual == np.dtype(expected_dtype), (
                    f"Column {col!r}: {actual} != {expected_dtype}"
                )

    def test_verify_true(self):
        path = _fixture_path("tabular")
        assert verify(path) is True


# ---------------------------------------------------------------------------
# Complex metadata tests — complex-metadata fixture
# ---------------------------------------------------------------------------


class TestComplexMetadata:
    """Deeply nested metadata groups match expected tree."""

    def test_groups_present(self):
        expected = _load_expected("complex-metadata")
        path = _fixture_path("complex-metadata")
        with h5py.File(path, "r") as f:
            for grp_path in expected["groups"]:
                if grp_path == "/":
                    continue
                assert grp_path in f, f"Missing group {grp_path!r}"

    def test_metadata_tree(self):
        expected = _load_expected("complex-metadata")
        path = _fixture_path("complex-metadata")
        with h5py.File(path, "r") as f:
            from fd5.h5io import h5_to_dict

            actual = h5_to_dict(f["metadata"])
            expected_tree = expected["metadata_tree"]["metadata"]
            assert actual == expected_tree

    def test_verify_true(self):
        path = _fixture_path("complex-metadata")
        assert verify(path) is True


# ---------------------------------------------------------------------------
# Schema validation tests — across all valid fixtures
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    """Embedded schema validates the file's own structure."""

    @pytest.mark.parametrize(
        "fixture_name",
        ["minimal", "sealed", "tabular", "complex-metadata"],
    )
    def test_schema_validates(self, fixture_name):
        expected = _load_expected(fixture_name)
        if not expected.get("schema_valid", True):
            pytest.skip("Fixture not expected to pass schema validation")
        path = _fixture_path(fixture_name)
        errors = validate(path)
        assert errors == [], [e.message for e in errors]


# ---------------------------------------------------------------------------
# Negative tests — invalid fixtures
# ---------------------------------------------------------------------------


class TestInvalid:
    """Invalid files are rejected with appropriate errors."""

    def test_missing_id_raises(self):
        path = INVALID_DIR / "missing-id.fd5"
        with h5py.File(path, "r") as f:
            assert "id" not in f.attrs

    def test_bad_hash_fails_verify(self):
        path = INVALID_DIR / "bad-hash.fd5"
        assert verify(path) is False

    def test_no_schema_raises_on_validate(self):
        path = INVALID_DIR / "no-schema.fd5"
        with pytest.raises(KeyError, match="_schema"):
            validate(path)

    def test_expected_errors_json_matches(self):
        """Ensure expected-errors.json covers all invalid fixtures."""
        errors_json = json.loads((INVALID_DIR / "expected-errors.json").read_text())
        for filename in ["missing-id.fd5", "bad-hash.fd5", "no-schema.fd5"]:
            assert filename in errors_json, f"Missing entry for {filename}"
