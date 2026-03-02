"""fd5.audit -- audit log data model, read/write, and chain verification.

Implements the tamper-evident audit trail stored as a JSON array in the
``_fd5_audit_log`` root attribute.  Each entry records the ``parent_hash``
(content_hash *before* the edit), author identity, timestamp, human-readable
message, and a list of attribute-level changes.

The audit log is *not* excluded from the Merkle-tree content_hash computation,
making the chain tamper-evident: altering any entry invalidates the seal.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Union

import h5py

from fd5.hash import compute_content_hash

_AUDIT_LOG_ATTR = "_fd5_audit_log"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class AuditEntry:
    """A single entry in the fd5 audit log."""

    parent_hash: str
    timestamp: str
    author: dict[str, str]
    message: str
    changes: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return {
            "parent_hash": self.parent_hash,
            "timestamp": self.timestamp,
            "author": dict(self.author),
            "message": self.message,
            "changes": [dict(c) for c in self.changes],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AuditEntry:
        """Deserialise from a dict (e.g. parsed JSON)."""
        return cls(
            parent_hash=d["parent_hash"],
            timestamp=d["timestamp"],
            author=d["author"],
            message=d["message"],
            changes=d["changes"],
        )


@dataclasses.dataclass
class ChainStatus:
    """Result of audit-chain verification."""

    status: str  # "valid", "broken", "no_log"
    detail: str = ""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_entry(entry: AuditEntry) -> None:
    """Raise :class:`ValueError` if *entry* is structurally invalid."""
    if not entry.parent_hash:
        raise ValueError("parent_hash must not be empty")
    if not entry.timestamp:
        raise ValueError("timestamp must not be empty")
    if "type" not in entry.author:
        raise ValueError("author dict must contain 'type' key")


# ---------------------------------------------------------------------------
# Read / Write
# ---------------------------------------------------------------------------


def read_audit_log(file: h5py.File) -> list[AuditEntry]:
    """Read the audit log from an open HDF5 file.

    Returns an empty list when the attribute is absent or contains ``[]``.
    Raises :class:`ValueError` on malformed JSON.
    """
    raw = file.attrs.get(_AUDIT_LOG_ATTR)
    if raw is None:
        return []

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    try:
        entries_raw = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {_AUDIT_LOG_ATTR}: {exc}") from exc

    return [AuditEntry.from_dict(d) for d in entries_raw]


def append_audit_entry(file: h5py.File, entry: AuditEntry) -> None:
    """Append *entry* to the audit log stored in *file*.

    Creates the ``_fd5_audit_log`` attribute if it does not yet exist.
    """
    existing = read_audit_log(file)
    existing.append(entry)
    serialised = json.dumps([e.to_dict() for e in existing], separators=(",", ":"))
    file.attrs[_AUDIT_LOG_ATTR] = serialised


# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------


def _undo_changes(
    f: h5py.File,
    entries: list[AuditEntry],
    from_idx: int,
) -> None:
    """Undo attribute changes from entries[from_idx..N) in reverse order.

    This reconstructs the file state *before* entry ``from_idx`` was applied
    by reverting each change's ``new`` value back to its ``old`` value.
    """
    for entry in reversed(entries[from_idx:]):
        for change in reversed(entry.changes):
            path = change.get("path", "/")
            attr = change.get("attr", "")
            old_val = change.get("old", "")
            if not attr:
                continue
            obj = f if path == "/" else f[path]
            obj.attrs[attr] = old_val


def _redo_changes(
    f: h5py.File,
    entries: list[AuditEntry],
    from_idx: int,
) -> None:
    """Re-apply attribute changes from entries[from_idx..N) in forward order.

    This restores the file state *after* all entries have been applied.
    """
    for entry in entries[from_idx:]:
        for change in entry.changes:
            path = change.get("path", "/")
            attr = change.get("attr", "")
            new_val = change.get("new", "")
            if not attr:
                continue
            obj = f if path == "/" else f[path]
            obj.attrs[attr] = new_val


def verify_chain(path: Union[str, Path]) -> ChainStatus:
    """Verify the audit-chain integrity of an fd5 file.

    Algorithm
    ---------
    For a chain of *N* entries the verification reconstructs each
    intermediate file state by undoing attribute changes recorded in
    the audit log:

    1. To verify entry *i*, undo all changes from entries[i..N) in
       reverse order, set the log to entries[0..i), and compute
       ``content_hash``.  The result must equal entry[i].parent_hash.
    2. For entry 0, the log is stripped entirely and all changes are
       undone, giving the genesis state.
    3. After each check, all changes are re-applied to restore the
       current state.

    Returns a :class:`ChainStatus` with ``status`` one of
    ``"valid"``, ``"broken"``, ``"no_log"``.
    """
    path = Path(path)

    with h5py.File(path, "r") as f:
        entries = read_audit_log(f)

    if not entries:
        return ChainStatus(status="no_log")

    # Work on a copy to avoid mutating the original.
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_file = Path(tmpdir) / path.name
        shutil.copy2(path, tmp_file)

        with h5py.File(tmp_file, "a") as f:
            original_log_raw = f.attrs.get(_AUDIT_LOG_ATTR)

            for i in range(len(entries)):
                # Undo changes from entries[i..N)
                _undo_changes(f, entries, i)

                # Set log to entries[0..i)
                if i == 0:
                    if _AUDIT_LOG_ATTR in f.attrs:
                        del f.attrs[_AUDIT_LOG_ATTR]
                else:
                    partial_log = json.dumps(
                        [e.to_dict() for e in entries[:i]],
                        separators=(",", ":"),
                    )
                    f.attrs[_AUDIT_LOG_ATTR] = partial_log

                expected_hash = compute_content_hash(f)

                # Restore: re-apply changes and full log
                _redo_changes(f, entries, i)
                if original_log_raw is not None:
                    f.attrs[_AUDIT_LOG_ATTR] = original_log_raw

                if entries[i].parent_hash != expected_hash:
                    return ChainStatus(
                        status="broken",
                        detail=(
                            f"Entry {i} parent_hash mismatch: "
                            f"expected {expected_hash}, "
                            f"got {entries[i].parent_hash}"
                        ),
                    )

    return ChainStatus(status="valid")
