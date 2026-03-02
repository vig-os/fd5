"""fd5.hash — id computation, Merkle tree hashing, and integrity verification.

Implements the content_hash computation described in white-paper.md
§ content_hash computation — Merkle tree with per-chunk hashing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Union

import h5py
import numpy as np

_CHUNK_HASHES_SUFFIX = "_chunk_hashes"
_EXCLUDED_ATTRS = frozenset({"content_hash"})


# ---------------------------------------------------------------------------
# id computation
# ---------------------------------------------------------------------------


def compute_id(inputs: dict[str, str], id_inputs_desc: str) -> str:
    """Compute ``sha256:...`` identity hash from *inputs* joined with ``\\0``.

    Keys are sorted for determinism.  *id_inputs_desc* is the human-readable
    description stored alongside the hash (not used in the hash itself).
    """
    payload = "\0".join(inputs[k] for k in sorted(inputs))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# ---------------------------------------------------------------------------
# ChunkHasher — per-chunk SHA-256 accumulator
# ---------------------------------------------------------------------------


class ChunkHasher:
    """Accumulates per-chunk SHA-256 hashes during streaming writes."""

    def __init__(self) -> None:
        self._digests: list[str] = []

    def update(self, chunk: np.ndarray) -> None:
        """Hash *chunk* (row-major ``tobytes()``) and store the digest."""
        self._digests.append(hashlib.sha256(chunk.tobytes()).hexdigest())

    def digests(self) -> list[str]:
        """Return the list of per-chunk hex digests accumulated so far."""
        return list(self._digests)

    def dataset_hash(self) -> str:
        """Compute the dataset-level hash from accumulated chunk hashes.

        ``sha256(chunk_hash_0 + chunk_hash_1 + ...)``
        """
        if not self._digests:
            raise ValueError("Cannot compute dataset_hash: no chunks recorded")
        concatenated = "".join(self._digests)
        return hashlib.sha256(concatenated.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# MerkleTree — bottom-up hash of an HDF5 file
# ---------------------------------------------------------------------------


def _is_chunk_hashes_dataset(name: str) -> bool:
    return name.endswith(_CHUNK_HASHES_SUFFIX)


def _serialize_attr(value: object) -> bytes:
    """Deterministic byte serialisation of a single HDF5 attribute value."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, np.ndarray):
        return value.tobytes()
    if isinstance(value, (np.generic,)):
        return np.array(value).tobytes()
    return str(value).encode("utf-8")


def _sorted_attrs_hash(obj: h5py.Group | h5py.Dataset) -> str:
    """``sha256(sha256(key + serialize(val)) for key in sorted(attrs))``."""
    h = hashlib.sha256()
    for key in sorted(obj.attrs.keys()):
        if key in _EXCLUDED_ATTRS:
            continue
        inner = hashlib.sha256(
            key.encode("utf-8") + _serialize_attr(obj.attrs[key])
        ).hexdigest()
        h.update(inner.encode("utf-8"))
    return h.hexdigest()


def _dataset_hash(ds: h5py.Dataset) -> str:
    """Hash a dataset: read all data as contiguous row-major bytes.

    For chunked datasets the result is identical to hashing the whole
    array because ``ds[...].tobytes()`` always returns row-major bytes
    regardless of on-disk chunk layout.  Dataset attributes are hashed
    separately via the group-level Merkle node.
    """
    data_hash = hashlib.sha256(ds[...].tobytes()).hexdigest()
    attrs_h = _sorted_attrs_hash(ds)
    return hashlib.sha256((attrs_h + data_hash).encode("utf-8")).hexdigest()


def _group_hash(group: h5py.Group) -> str:
    """Recursively compute the Merkle hash of *group*.

    ``sha256(sorted_attrs_hash + child_hashes)`` where children are
    processed in sorted key order, ``_chunk_hashes`` datasets are excluded.
    """
    h = hashlib.sha256()
    h.update(_sorted_attrs_hash(group).encode("utf-8"))

    for key in sorted(group.keys()):
        if _is_chunk_hashes_dataset(key):
            continue
        link = group.get(key, getlink=True)
        if isinstance(link, h5py.ExternalLink):
            continue
        child = group[key]
        if isinstance(child, h5py.Group):
            h.update(_group_hash(child).encode("utf-8"))
        elif isinstance(child, h5py.Dataset):
            h.update(_dataset_hash(child).encode("utf-8"))

    return h.hexdigest()


def _dataset_hash_cached(ds: h5py.Dataset, data_hash: str) -> str:
    """Like :func:`_dataset_hash` but uses a pre-computed *data_hash*."""
    attrs_h = _sorted_attrs_hash(ds)
    return hashlib.sha256((attrs_h + data_hash).encode("utf-8")).hexdigest()


def _group_hash_cached(group: h5py.Group, cache: dict[str, str]) -> str:
    """Like :func:`_group_hash` but looks up dataset data hashes in *cache*."""
    h = hashlib.sha256()
    h.update(_sorted_attrs_hash(group).encode("utf-8"))

    for key in sorted(group.keys()):
        if _is_chunk_hashes_dataset(key):
            continue
        link = group.get(key, getlink=True)
        if isinstance(link, h5py.ExternalLink):
            continue
        child = group[key]
        if isinstance(child, h5py.Group):
            h.update(_group_hash_cached(child, cache).encode("utf-8"))
        elif isinstance(child, h5py.Dataset):
            if child.name in cache:
                h.update(_dataset_hash_cached(child, cache[child.name]).encode("utf-8"))
            else:
                h.update(_dataset_hash(child).encode("utf-8"))

    return h.hexdigest()


class MerkleTree:
    """Computes the Merkle root hash of an HDF5 file/group.

    Follows the algorithm in white-paper.md § File-level Merkle tree:
    ``content_hash = sha256(root_group_hash)``.
    """

    def __init__(self, root: h5py.File | h5py.Group) -> None:
        self._root = root

    def root_hash(self) -> str:
        """Return the 64-char hex Merkle root."""
        return hashlib.sha256(_group_hash(self._root).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def compute_content_hash(
    root: h5py.File | h5py.Group,
    data_hash_cache: dict[str, str] | None = None,
) -> str:
    """Return the algorithm-prefixed content hash: ``sha256:<hex>``.

    When *data_hash_cache* is provided, datasets whose absolute HDF5 path
    appears in the mapping use the cached ``sha256(data.tobytes())`` hex
    digest instead of re-reading the dataset.  Datasets not in the cache
    fall back to the standard full-read path.
    """
    if data_hash_cache:
        root_h = _group_hash_cached(root, data_hash_cache)
    else:
        root_h = _group_hash(root)
    return f"sha256:{hashlib.sha256(root_h.encode('utf-8')).hexdigest()}"


def verify(path: Union[str, Path]) -> bool:
    """Recompute the Merkle tree and compare with the stored ``content_hash``.

    Returns ``True`` if the hashes match, ``False`` otherwise (including
    when ``content_hash`` is missing).
    """
    path = Path(path)
    with h5py.File(path, "r") as f:
        stored = f.attrs.get("content_hash")
        if stored is None:
            return False
        if isinstance(stored, bytes):
            stored = stored.decode("utf-8")
        return compute_content_hash(f) == stored
