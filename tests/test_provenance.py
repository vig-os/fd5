"""Tests for fd5.provenance — write_sources, write_original_files, write_ingest."""

from __future__ import annotations

import h5py
import pytest

from fd5.provenance import write_ingest, write_original_files, write_sources


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def h5file(tmp_path):
    """Yield a writable HDF5 file, auto-closed after test."""
    path = tmp_path / "test.h5"
    with h5py.File(path, "w") as f:
        yield f


# ---------------------------------------------------------------------------
# write_sources
# ---------------------------------------------------------------------------


class TestWriteSources:
    """write_sources creates sources/ group with sub-groups, attrs, and external links."""

    def _make_source(self, **overrides):
        defaults = {
            "name": "emission",
            "id": "sha256:def67890abcdef1234567890abcdef1234567890abcdef1234567890abcdef12",
            "product": "listmode",
            "file": "2024-07-24_19-06-10_listmode-def67890_pet_coinc.h5",
            "content_hash": "sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "role": "emission_data",
            "description": "PET listmode coincidence data used for reconstruction",
        }
        defaults.update(overrides)
        return defaults

    def test_creates_sources_group(self, h5file):
        write_sources(h5file, [self._make_source()])
        assert "sources" in h5file

    def test_sources_group_has_description(self, h5file):
        write_sources(h5file, [self._make_source()])
        assert "description" in h5file["sources"].attrs

    def test_creates_named_subgroup(self, h5file):
        write_sources(h5file, [self._make_source(name="emission")])
        assert "emission" in h5file["sources"]

    def test_subgroup_has_required_attrs(self, h5file):
        src = self._make_source()
        write_sources(h5file, [src])
        grp = h5file["sources/emission"]
        assert grp.attrs["id"] == src["id"]
        assert grp.attrs["product"] == src["product"]
        assert grp.attrs["file"] == src["file"]
        assert grp.attrs["content_hash"] == src["content_hash"]
        assert grp.attrs["role"] == src["role"]
        assert grp.attrs["description"] == src["description"]

    def test_subgroup_has_external_link(self, h5file):
        src = self._make_source()
        write_sources(h5file, [src])
        link = h5file["sources/emission"].get("link", getlink=True)
        assert isinstance(link, h5py.ExternalLink)

    def test_external_link_uses_relative_path(self, h5file):
        src = self._make_source(file="subdir/some_file.h5")
        write_sources(h5file, [src])
        link = h5file["sources/emission"].get("link", getlink=True)
        assert link.filename == "subdir/some_file.h5"
        assert link.path == "/"

    def test_multiple_sources(self, h5file):
        sources = [
            self._make_source(name="emission"),
            self._make_source(
                name="attenuation",
                product="recon",
                file="2024-07-24_18-25-00_recon-21d255e7_ct_ctac.h5",
                role="mu_map",
                description="CT reconstruction for attenuation correction",
            ),
        ]
        write_sources(h5file, sources)
        assert "emission" in h5file["sources"]
        assert "attenuation" in h5file["sources"]

    def test_empty_sources_list(self, h5file):
        write_sources(h5file, [])
        assert "sources" in h5file
        assert len(h5file["sources"]) == 0

    def test_name_key_not_stored_as_attr(self, h5file):
        write_sources(h5file, [self._make_source()])
        grp = h5file["sources/emission"]
        assert "name" not in grp.attrs


# ---------------------------------------------------------------------------
# write_original_files
# ---------------------------------------------------------------------------


class TestWriteOriginalFiles:
    """write_original_files creates provenance/original_files compound dataset."""

    def _make_record(self, **overrides):
        defaults = {
            "path": "/data/raw/scan_001.dcm",
            "sha256": "sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "size_bytes": 1048576,
        }
        defaults.update(overrides)
        return defaults

    def test_creates_provenance_group(self, h5file):
        write_original_files(h5file, [self._make_record()])
        assert "provenance" in h5file

    def test_provenance_group_has_description(self, h5file):
        write_original_files(h5file, [self._make_record()])
        assert "description" in h5file["provenance"].attrs

    def test_creates_original_files_dataset(self, h5file):
        write_original_files(h5file, [self._make_record()])
        assert "original_files" in h5file["provenance"]

    def test_dataset_is_compound_type(self, h5file):
        write_original_files(h5file, [self._make_record()])
        ds = h5file["provenance/original_files"]
        assert ds.dtype.names is not None
        assert "path" in ds.dtype.names
        assert "sha256" in ds.dtype.names
        assert "size_bytes" in ds.dtype.names

    def test_single_record_values(self, h5file):
        rec = self._make_record()
        write_original_files(h5file, [rec])
        ds = h5file["provenance/original_files"]
        assert len(ds) == 1
        row = ds[0]
        assert row["path"].decode("utf-8") == rec["path"]
        assert row["sha256"].decode("utf-8") == rec["sha256"]
        assert int(row["size_bytes"]) == rec["size_bytes"]

    def test_multiple_records(self, h5file):
        records = [
            self._make_record(path="/data/raw/scan_001.dcm", size_bytes=100),
            self._make_record(path="/data/raw/scan_002.dcm", size_bytes=200),
        ]
        write_original_files(h5file, records)
        ds = h5file["provenance/original_files"]
        assert len(ds) == 2

    def test_empty_records(self, h5file):
        write_original_files(h5file, [])
        ds = h5file["provenance/original_files"]
        assert len(ds) == 0

    def test_preserves_existing_provenance_group(self, h5file):
        h5file.create_group("provenance")
        h5file["provenance"].attrs["existing"] = "keep"
        write_original_files(h5file, [self._make_record()])
        assert h5file["provenance"].attrs["existing"] == "keep"


# ---------------------------------------------------------------------------
# write_ingest
# ---------------------------------------------------------------------------


class TestWriteIngest:
    """write_ingest writes provenance/ingest/ group attrs."""

    def test_creates_provenance_ingest_group(self, h5file):
        write_ingest(
            h5file,
            tool="duplet_ingest",
            version="0.3.1",
            timestamp="2026-02-11T15:00:00+01:00",
        )
        assert "provenance" in h5file
        assert "ingest" in h5file["provenance"]

    def test_ingest_attrs(self, h5file):
        write_ingest(
            h5file,
            tool="duplet_ingest",
            version="0.3.1",
            timestamp="2026-02-11T15:00:00+01:00",
        )
        grp = h5file["provenance/ingest"]
        assert grp.attrs["tool"] == "duplet_ingest"
        assert grp.attrs["tool_version"] == "0.3.1"
        assert grp.attrs["timestamp"] == "2026-02-11T15:00:00+01:00"

    def test_ingest_has_description(self, h5file):
        write_ingest(
            h5file,
            tool="duplet_ingest",
            version="0.3.1",
            timestamp="2026-02-11T15:00:00+01:00",
        )
        grp = h5file["provenance/ingest"]
        assert "description" in grp.attrs

    def test_preserves_existing_provenance_group(self, h5file):
        h5file.create_group("provenance")
        h5file["provenance"].attrs["existing"] = "keep"
        write_ingest(
            h5file, tool="test", version="1.0", timestamp="2026-01-01T00:00:00Z"
        )
        assert h5file["provenance"].attrs["existing"] == "keep"

    def test_coexists_with_original_files(self, h5file):
        write_original_files(
            h5file,
            [
                {
                    "path": "/data/file.dcm",
                    "sha256": "sha256:abc123",
                    "size_bytes": 42,
                }
            ],
        )
        write_ingest(
            h5file, tool="test", version="1.0", timestamp="2026-01-01T00:00:00Z"
        )
        assert "original_files" in h5file["provenance"]
        assert "ingest" in h5file["provenance"]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Calling writers twice should raise or produce consistent state."""

    def test_write_sources_twice_raises(self, h5file):
        src = [
            {
                "name": "emission",
                "id": "sha256:abc",
                "product": "listmode",
                "file": "file.h5",
                "content_hash": "sha256:def",
                "role": "emission_data",
                "description": "test",
            }
        ]
        write_sources(h5file, src)
        with pytest.raises((ValueError, RuntimeError)):
            write_sources(h5file, src)

    def test_write_original_files_twice_raises(self, h5file):
        rec = [{"path": "/f.dcm", "sha256": "sha256:abc", "size_bytes": 1}]
        write_original_files(h5file, rec)
        with pytest.raises((ValueError, RuntimeError)):
            write_original_files(h5file, rec)

    def test_write_ingest_twice_raises(self, h5file):
        write_ingest(h5file, tool="t", version="1", timestamp="2026-01-01T00:00:00Z")
        with pytest.raises((ValueError, RuntimeError)):
            write_ingest(
                h5file, tool="t", version="1", timestamp="2026-01-01T00:00:00Z"
            )
