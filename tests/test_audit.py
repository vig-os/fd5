"""Tests for fd5.audit -- audit log data model, read/write, and chain verification."""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from fd5.hash import compute_content_hash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def h5file(tmp_path: Path):
    """Yield a writable HDF5 file, auto-closed after test."""
    path = tmp_path / "test.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path: Path) -> Path:
    """Return a path for creating HDF5 files."""
    return tmp_path / "test.h5"


@pytest.fixture()
def sealed_h5(tmp_path: Path) -> Path:
    """Create a minimal sealed fd5 file with content_hash."""
    path = tmp_path / "sealed.h5"
    with h5py.File(path, "w") as f:
        f.attrs["product"] = "test/recon"
        f.attrs["name"] = "test file"
        f.create_dataset("volume", data=np.zeros((4, 4), dtype=np.float32))
        f.attrs["content_hash"] = compute_content_hash(f)
    return path


# ---------------------------------------------------------------------------
# AuditEntry dataclass
# ---------------------------------------------------------------------------


class TestAuditEntry:
    def test_create_entry(self):
        from fd5.audit import AuditEntry

        entry = AuditEntry(
            parent_hash="sha256:abc123",
            timestamp="2026-03-02T14:30:00Z",
            author={"type": "orcid", "id": "0000-0001-2345-6789", "name": "Lars"},
            message="Updated calibration factor",
            changes=[
                {
                    "action": "edit",
                    "path": "/group",
                    "attr": "name",
                    "old": "1.0",
                    "new": "1.05",
                }
            ],
        )
        assert entry.parent_hash == "sha256:abc123"
        assert entry.timestamp == "2026-03-02T14:30:00Z"
        assert entry.author["name"] == "Lars"
        assert entry.message == "Updated calibration factor"
        assert len(entry.changes) == 1

    def test_to_dict_roundtrip(self):
        from fd5.audit import AuditEntry

        entry = AuditEntry(
            parent_hash="sha256:abc123",
            timestamp="2026-03-02T14:30:00Z",
            author={"type": "orcid", "id": "0000-0001-2345-6789", "name": "Lars"},
            message="Updated calibration factor",
            changes=[
                {
                    "action": "edit",
                    "path": "/group",
                    "attr": "name",
                    "old": "1.0",
                    "new": "1.05",
                }
            ],
        )
        d = entry.to_dict()
        restored = AuditEntry.from_dict(d)
        assert restored.parent_hash == entry.parent_hash
        assert restored.timestamp == entry.timestamp
        assert restored.author == entry.author
        assert restored.message == entry.message
        assert restored.changes == entry.changes

    def test_to_dict_keys(self):
        from fd5.audit import AuditEntry

        entry = AuditEntry(
            parent_hash="sha256:abc",
            timestamp="2026-03-02T14:30:00Z",
            author={"type": "anonymous", "id": "", "name": "Anonymous"},
            message="test",
            changes=[],
        )
        d = entry.to_dict()
        assert set(d.keys()) == {
            "parent_hash",
            "timestamp",
            "author",
            "message",
            "changes",
        }

    def test_from_dict_missing_field_raises(self):
        from fd5.audit import AuditEntry

        with pytest.raises((KeyError, TypeError)):
            AuditEntry.from_dict({"parent_hash": "sha256:abc"})

    def test_entry_validation_empty_parent_hash(self):
        """AuditEntry requires a non-empty parent_hash."""
        from fd5.audit import AuditEntry, validate_entry

        entry = AuditEntry(
            parent_hash="",
            timestamp="2026-03-02T14:30:00Z",
            author={"type": "anonymous", "id": "", "name": "Anonymous"},
            message="test",
            changes=[],
        )
        with pytest.raises(ValueError, match="parent_hash"):
            validate_entry(entry)

    def test_entry_validation_empty_timestamp(self):
        """AuditEntry requires a non-empty timestamp."""
        from fd5.audit import AuditEntry, validate_entry

        entry = AuditEntry(
            parent_hash="sha256:abc",
            timestamp="",
            author={"type": "anonymous", "id": "", "name": "Anonymous"},
            message="test",
            changes=[],
        )
        with pytest.raises(ValueError, match="timestamp"):
            validate_entry(entry)

    def test_entry_validation_missing_author_type(self):
        """AuditEntry author dict must contain 'type'."""
        from fd5.audit import AuditEntry, validate_entry

        entry = AuditEntry(
            parent_hash="sha256:abc",
            timestamp="2026-03-02T14:30:00Z",
            author={"id": "0000", "name": "Lars"},
            message="test",
            changes=[],
        )
        with pytest.raises(ValueError, match="author"):
            validate_entry(entry)

    def test_entry_validation_valid_passes(self):
        """A well-formed entry should pass validation without error."""
        from fd5.audit import AuditEntry, validate_entry

        entry = AuditEntry(
            parent_hash="sha256:abc",
            timestamp="2026-03-02T14:30:00Z",
            author={"type": "orcid", "id": "0000-0001-2345-6789", "name": "Lars"},
            message="test",
            changes=[],
        )
        validate_entry(entry)  # should not raise


# ---------------------------------------------------------------------------
# read_audit_log / append_audit_entry
# ---------------------------------------------------------------------------


class TestReadAuditLog:
    def test_read_empty_log(self, h5file):
        """Reading from a file with no audit log returns empty list."""
        from fd5.audit import read_audit_log

        entries = read_audit_log(h5file)
        assert entries == []

    def test_read_empty_json_array(self, h5file):
        """Reading from a file with an empty JSON array returns empty list."""
        from fd5.audit import read_audit_log

        h5file.attrs["_fd5_audit_log"] = "[]"
        entries = read_audit_log(h5file)
        assert entries == []

    def test_malformed_json_error(self, h5file):
        """Malformed JSON in the audit log attribute raises ValueError."""
        from fd5.audit import read_audit_log

        h5file.attrs["_fd5_audit_log"] = "{not valid json"
        with pytest.raises(ValueError, match="malformed"):
            read_audit_log(h5file)


class TestAppendAuditEntry:
    def test_append_creates_attribute(self, h5file):
        """First append creates the _fd5_audit_log attribute."""
        from fd5.audit import AuditEntry, append_audit_entry

        entry = AuditEntry(
            parent_hash="sha256:abc",
            timestamp="2026-03-02T14:30:00Z",
            author={"type": "anonymous", "id": "", "name": "Anonymous"},
            message="first entry",
            changes=[],
        )
        append_audit_entry(h5file, entry)
        assert "_fd5_audit_log" in h5file.attrs

    def test_append_roundtrip(self, h5file):
        """Appended entry can be read back identically."""
        from fd5.audit import AuditEntry, append_audit_entry, read_audit_log

        entry = AuditEntry(
            parent_hash="sha256:abc123",
            timestamp="2026-03-02T14:30:00Z",
            author={"type": "orcid", "id": "0000-0001-2345-6789", "name": "Lars"},
            message="Updated calibration factor",
            changes=[
                {
                    "action": "edit",
                    "path": "/group",
                    "attr": "cal_factor",
                    "old": "1.0",
                    "new": "1.05",
                }
            ],
        )
        append_audit_entry(h5file, entry)
        entries = read_audit_log(h5file)
        assert len(entries) == 1
        assert entries[0].parent_hash == "sha256:abc123"
        assert entries[0].message == "Updated calibration factor"
        assert entries[0].changes[0]["new"] == "1.05"

    def test_append_to_existing_log(self, h5file):
        """Appending to an existing log preserves earlier entries."""
        from fd5.audit import AuditEntry, append_audit_entry, read_audit_log

        entry1 = AuditEntry(
            parent_hash="sha256:first",
            timestamp="2026-03-01T10:00:00Z",
            author={"type": "anonymous", "id": "", "name": "Anonymous"},
            message="first",
            changes=[],
        )
        entry2 = AuditEntry(
            parent_hash="sha256:second",
            timestamp="2026-03-02T10:00:00Z",
            author={"type": "anonymous", "id": "", "name": "Anonymous"},
            message="second",
            changes=[],
        )
        append_audit_entry(h5file, entry1)
        append_audit_entry(h5file, entry2)
        entries = read_audit_log(h5file)
        assert len(entries) == 2
        assert entries[0].message == "first"
        assert entries[1].message == "second"

    def test_stored_as_json_string(self, h5file):
        """The audit log is stored as a JSON string, not binary."""
        from fd5.audit import AuditEntry, append_audit_entry

        entry = AuditEntry(
            parent_hash="sha256:abc",
            timestamp="2026-03-02T14:30:00Z",
            author={"type": "anonymous", "id": "", "name": "Anonymous"},
            message="test",
            changes=[],
        )
        append_audit_entry(h5file, entry)
        raw = h5file.attrs["_fd5_audit_log"]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        parsed = json.loads(raw)
        assert isinstance(parsed, list)
        assert len(parsed) == 1


# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------


class TestVerifyChain:
    def test_no_log_returns_nolog(self, h5path: Path):
        """A file with no audit log returns 'no_log' status."""
        from fd5.audit import verify_chain

        with h5py.File(h5path, "w") as f:
            f.attrs["product"] = "test"
            f.attrs["content_hash"] = compute_content_hash(f)
        status = verify_chain(h5path)
        assert status.status == "no_log"

    def test_single_entry_chain_valid(self, sealed_h5: Path):
        """A single audit entry whose parent_hash matches the original content_hash is valid."""
        from fd5.audit import AuditEntry, append_audit_entry, verify_chain

        # Read the original hash before modification
        with h5py.File(sealed_h5, "r") as f:
            original_hash = f.attrs["content_hash"]
            if isinstance(original_hash, bytes):
                original_hash = original_hash.decode("utf-8")

        # Append an audit entry with parent_hash = original content_hash, then reseal
        with h5py.File(sealed_h5, "a") as f:
            entry = AuditEntry(
                parent_hash=original_hash,
                timestamp="2026-03-02T14:30:00Z",
                author={"type": "anonymous", "id": "", "name": "Anonymous"},
                message="test edit",
                changes=[],
            )
            append_audit_entry(f, entry)
            # Reseal with new content_hash
            f.attrs["content_hash"] = compute_content_hash(f)

        status = verify_chain(sealed_h5)
        assert status.status == "valid"

    def test_tampered_entry_detected(self, sealed_h5: Path):
        """If the first entry's parent_hash doesn't match any plausible prior state, chain is broken."""
        from fd5.audit import AuditEntry, append_audit_entry, verify_chain

        with h5py.File(sealed_h5, "a") as f:
            entry = AuditEntry(
                parent_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
                timestamp="2026-03-02T14:30:00Z",
                author={"type": "anonymous", "id": "", "name": "Anonymous"},
                message="tampered entry",
                changes=[],
            )
            append_audit_entry(f, entry)
            f.attrs["content_hash"] = compute_content_hash(f)

        status = verify_chain(sealed_h5)
        assert status.status == "broken"

    def test_valid_chain_multiple_entries(self, tmp_path: Path):
        """A chain of two edits with correct parent hashes is valid.

        Chain verification undoes recorded attribute changes to reconstruct
        intermediate states and verify each entry's parent_hash.
        """
        from fd5.audit import AuditEntry, append_audit_entry, verify_chain

        path = tmp_path / "multi.h5"

        # Create initial file
        with h5py.File(path, "w") as f:
            f.attrs["product"] = "test"
            f.attrs["name"] = "original"
            f.create_dataset("data", data=np.array([1.0, 2.0]))
            f.attrs["content_hash"] = compute_content_hash(f)

        # First edit
        with h5py.File(path, "r") as f:
            hash_before_edit1 = f.attrs["content_hash"]
            if isinstance(hash_before_edit1, bytes):
                hash_before_edit1 = hash_before_edit1.decode("utf-8")

        with h5py.File(path, "a") as f:
            f.attrs["name"] = "modified"
            entry1 = AuditEntry(
                parent_hash=hash_before_edit1,
                timestamp="2026-03-01T10:00:00Z",
                author={"type": "anonymous", "id": "", "name": "Anonymous"},
                message="first edit",
                changes=[
                    {
                        "action": "edit",
                        "path": "/",
                        "attr": "name",
                        "old": "original",
                        "new": "modified",
                    }
                ],
            )
            append_audit_entry(f, entry1)
            f.attrs["content_hash"] = compute_content_hash(f)

        # Second edit
        with h5py.File(path, "r") as f:
            hash_before_edit2 = f.attrs["content_hash"]
            if isinstance(hash_before_edit2, bytes):
                hash_before_edit2 = hash_before_edit2.decode("utf-8")

        with h5py.File(path, "a") as f:
            f.attrs["name"] = "final"
            entry2 = AuditEntry(
                parent_hash=hash_before_edit2,
                timestamp="2026-03-02T10:00:00Z",
                author={"type": "anonymous", "id": "", "name": "Anonymous"},
                message="second edit",
                changes=[
                    {
                        "action": "edit",
                        "path": "/",
                        "attr": "name",
                        "old": "modified",
                        "new": "final",
                    }
                ],
            )
            append_audit_entry(f, entry2)
            f.attrs["content_hash"] = compute_content_hash(f)

        status = verify_chain(path)
        assert status.status == "valid"

    def test_broken_chain_middle_entry(self, tmp_path: Path):
        """If a middle entry has wrong parent_hash, chain is broken."""
        from fd5.audit import verify_chain

        path = tmp_path / "broken.h5"

        with h5py.File(path, "w") as f:
            f.attrs["product"] = "test"
            f.attrs["name"] = "original"
            f.create_dataset("data", data=np.array([1.0]))
            original_hash = compute_content_hash(f)
            f.attrs["content_hash"] = original_hash

        # Write a manually crafted log with a broken chain in the middle
        with h5py.File(path, "a") as f:
            log = [
                {
                    "parent_hash": original_hash,
                    "timestamp": "2026-03-01T10:00:00Z",
                    "author": {"type": "anonymous", "id": "", "name": "Anonymous"},
                    "message": "first edit",
                    "changes": [],
                },
                {
                    "parent_hash": "sha256:bogus_hash_that_does_not_match",
                    "timestamp": "2026-03-02T10:00:00Z",
                    "author": {"type": "anonymous", "id": "", "name": "Anonymous"},
                    "message": "second edit with wrong parent",
                    "changes": [],
                },
            ]
            f.attrs["_fd5_audit_log"] = json.dumps(log)
            f.attrs["content_hash"] = compute_content_hash(f)

        status = verify_chain(path)
        assert status.status == "broken"
