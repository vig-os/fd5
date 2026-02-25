"""Tests for fd5.hash — id computation, Merkle tree hashing, and integrity verification."""

from __future__ import annotations

import hashlib
from pathlib import Path

import h5py
import numpy as np
import pytest

from fd5.hash import (
    ChunkHasher,
    MerkleTree,
    compute_content_hash,
    compute_id,
    verify,
)


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


# ---------------------------------------------------------------------------
# compute_id
# ---------------------------------------------------------------------------


class TestComputeId:
    def test_basic(self):
        result = compute_id(
            {"product": "recon", "timestamp": "2026-01-15T10:00:00Z"},
            "product + timestamp",
        )
        expected_payload = "recon\0" + "2026-01-15T10:00:00Z"
        expected = (
            "sha256:" + hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()
        )
        assert result == expected

    def test_prefix_format(self):
        result = compute_id({"a": "1"}, "a")
        assert result.startswith("sha256:")
        hex_part = result[len("sha256:") :]
        assert len(hex_part) == 64

    def test_deterministic(self):
        inputs = {"x": "hello", "y": "world"}
        desc = "x + y"
        assert compute_id(inputs, desc) == compute_id(inputs, desc)

    def test_sorted_keys(self):
        r1 = compute_id({"b": "2", "a": "1"}, "a + b")
        r2 = compute_id({"a": "1", "b": "2"}, "a + b")
        assert r1 == r2

    def test_different_values_differ(self):
        r1 = compute_id({"a": "1"}, "a")
        r2 = compute_id({"a": "2"}, "a")
        assert r1 != r2

    def test_null_separator_prevents_collision(self):
        r1 = compute_id({"a": "12", "b": "3"}, "a + b")
        r2 = compute_id({"a": "1", "b": "23"}, "a + b")
        assert r1 != r2

    def test_single_input(self):
        result = compute_id({"key": "value"}, "key")
        expected = "sha256:" + hashlib.sha256(b"value").hexdigest()
        assert result == expected


# ---------------------------------------------------------------------------
# ChunkHasher
# ---------------------------------------------------------------------------


class TestChunkHasher:
    def test_single_chunk(self):
        data = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        hasher = ChunkHasher()
        hasher.update(data)
        hashes = hasher.digests()
        assert len(hashes) == 1
        expected = hashlib.sha256(data.tobytes()).hexdigest()
        assert hashes[0] == expected

    def test_multiple_chunks(self):
        hasher = ChunkHasher()
        chunks = [
            np.array([1.0, 2.0], dtype=np.float32),
            np.array([3.0, 4.0], dtype=np.float32),
        ]
        for c in chunks:
            hasher.update(c)

        hashes = hasher.digests()
        assert len(hashes) == 2
        for i, c in enumerate(chunks):
            assert hashes[i] == hashlib.sha256(c.tobytes()).hexdigest()

    def test_dataset_hash(self):
        hasher = ChunkHasher()
        c1 = np.array([1.0], dtype=np.float64)
        c2 = np.array([2.0], dtype=np.float64)
        hasher.update(c1)
        hasher.update(c2)

        h1 = hashlib.sha256(c1.tobytes()).hexdigest()
        h2 = hashlib.sha256(c2.tobytes()).hexdigest()
        expected = hashlib.sha256((h1 + h2).encode("utf-8")).hexdigest()
        assert hasher.dataset_hash() == expected

    def test_empty_raises(self):
        hasher = ChunkHasher()
        with pytest.raises(ValueError, match="no chunks"):
            hasher.dataset_hash()

    def test_row_major_bytes(self):
        data = np.array([[1, 2], [3, 4]], dtype=np.int32)
        hasher = ChunkHasher()
        hasher.update(data)
        expected = hashlib.sha256(data.tobytes()).hexdigest()
        assert hasher.digests()[0] == expected


# ---------------------------------------------------------------------------
# MerkleTree
# ---------------------------------------------------------------------------


class TestMerkleTree:
    def test_attrs_only(self, h5file: h5py.File):
        h5file.attrs["name"] = "test"
        h5file.attrs["count"] = np.int64(42)
        tree = MerkleTree(h5file)
        root = tree.root_hash()
        assert isinstance(root, str)
        assert len(root) == 64

    def test_excludes_content_hash_attr(self, h5file: h5py.File):
        h5file.attrs["name"] = "test"
        tree1 = MerkleTree(h5file)
        hash1 = tree1.root_hash()

        h5file.attrs["content_hash"] = "sha256:deadbeef"
        tree2 = MerkleTree(h5file)
        hash2 = tree2.root_hash()

        assert hash1 == hash2

    def test_excludes_chunk_hashes_datasets(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.create_dataset("volume", data=np.zeros((4, 4), dtype=np.float32))
            f.attrs["name"] = "test"

        with h5py.File(h5path, "r") as f:
            tree1 = MerkleTree(f)
            hash1 = tree1.root_hash()

        with h5py.File(h5path, "a") as f:
            dt = h5py.special_dtype(vlen=str)
            f.create_dataset(
                "volume_chunk_hashes",
                data=np.array(["abc123"], dtype=object),
                dtype=dt,
            )

        with h5py.File(h5path, "r") as f:
            tree2 = MerkleTree(f)
            hash2 = tree2.root_hash()

        assert hash1 == hash2

    def test_sorted_keys_deterministic(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.attrs["z_attr"] = "last"
            f.attrs["a_attr"] = "first"
            f.create_dataset("z_data", data=np.array([1.0]))
            f.create_dataset("a_data", data=np.array([2.0]))

        with h5py.File(h5path, "r") as f:
            hash1 = MerkleTree(f).root_hash()

        with h5py.File(h5path, "r") as f:
            hash2 = MerkleTree(f).root_hash()

        assert hash1 == hash2

    def test_different_data_different_hash(self, tmp_path: Path):
        p1 = tmp_path / "a.h5"
        p2 = tmp_path / "b.h5"

        with h5py.File(p1, "w") as f:
            f.create_dataset("d", data=np.array([1.0]))
        with h5py.File(p2, "w") as f:
            f.create_dataset("d", data=np.array([2.0]))

        with h5py.File(p1, "r") as f1, h5py.File(p2, "r") as f2:
            assert MerkleTree(f1).root_hash() != MerkleTree(f2).root_hash()

    def test_different_attrs_different_hash(self, tmp_path: Path):
        p1 = tmp_path / "a.h5"
        p2 = tmp_path / "b.h5"

        with h5py.File(p1, "w") as f:
            f.attrs["val"] = "hello"
        with h5py.File(p2, "w") as f:
            f.attrs["val"] = "world"

        with h5py.File(p1, "r") as f1, h5py.File(p2, "r") as f2:
            assert MerkleTree(f1).root_hash() != MerkleTree(f2).root_hash()

    def test_nested_groups(self, h5file: h5py.File):
        g = h5file.create_group("metadata")
        g.attrs["version"] = np.int64(1)
        g.create_dataset("data", data=np.array([1, 2, 3]))

        tree = MerkleTree(h5file)
        root = tree.root_hash()
        assert isinstance(root, str)
        assert len(root) == 64

    def test_dataset_with_chunks(self, h5file: h5py.File):
        h5file.create_dataset(
            "volume",
            data=np.zeros((10, 4), dtype=np.float32),
            chunks=(2, 4),
        )
        tree = MerkleTree(h5file)
        root = tree.root_hash()
        assert isinstance(root, str)
        assert len(root) == 64

    def test_non_chunked_dataset(self, h5file: h5py.File):
        h5file.create_dataset("scalar", data=np.float64(3.14))
        tree = MerkleTree(h5file)
        root = tree.root_hash()
        assert isinstance(root, str)

    def test_empty_file(self, h5file: h5py.File):
        tree = MerkleTree(h5file)
        root = tree.root_hash()
        assert isinstance(root, str)
        assert len(root) == 64


# ---------------------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------------------


class TestComputeContentHash:
    def test_returns_prefixed_hash(self, h5file: h5py.File):
        h5file.create_dataset("data", data=np.array([1.0, 2.0, 3.0]))
        result = compute_content_hash(h5file)
        assert result.startswith("sha256:")
        assert len(result) == len("sha256:") + 64

    def test_deterministic(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.create_dataset("d", data=np.array([1, 2, 3]))
            f.attrs["name"] = "test"

        with h5py.File(h5path, "r") as f:
            h1 = compute_content_hash(f)
        with h5py.File(h5path, "r") as f:
            h2 = compute_content_hash(f)

        assert h1 == h2

    def test_ignores_content_hash_attr(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.create_dataset("d", data=np.array([1.0]))
            h1 = compute_content_hash(f)
            f.attrs["content_hash"] = h1

        with h5py.File(h5path, "r") as f:
            h2 = compute_content_hash(f)

        assert h1 == h2


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_valid_file(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.create_dataset("data", data=np.array([1.0, 2.0, 3.0]))
            f.attrs["name"] = "test"
            f.attrs["content_hash"] = compute_content_hash(f)

        assert verify(h5path) is True

    def test_corrupted_attr(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.create_dataset("data", data=np.array([1.0, 2.0, 3.0]))
            f.attrs["name"] = "test"
            f.attrs["content_hash"] = compute_content_hash(f)

        with h5py.File(h5path, "a") as f:
            f.attrs["name"] = "tampered"

        assert verify(h5path) is False

    def test_corrupted_data(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.create_dataset("data", data=np.array([1.0, 2.0, 3.0]))
            f.attrs["content_hash"] = compute_content_hash(f)

        with h5py.File(h5path, "a") as f:
            f["data"][0] = 999.0

        assert verify(h5path) is False

    def test_missing_content_hash(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.create_dataset("data", data=np.array([1.0]))

        assert verify(h5path) is False

    def test_accepts_path_string(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.attrs["content_hash"] = compute_content_hash(f)

        assert verify(str(h5path)) is True

    def test_complex_file(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.attrs["product"] = "recon"
            f.attrs["version"] = np.int64(1)
            g = f.create_group("metadata")
            g.attrs["algorithm"] = "osem"
            g.attrs["iterations"] = np.int64(4)
            f.create_dataset(
                "volume",
                data=np.random.default_rng(42).standard_normal(
                    (8, 8, 8), dtype=np.float32
                ),
                chunks=(2, 8, 8),
            )
            f.create_dataset("scalar", data=np.float64(1.5))
            f.attrs["content_hash"] = compute_content_hash(f)

        assert verify(h5path) is True

    def test_idempotent(self, h5path: Path):
        with h5py.File(h5path, "w") as f:
            f.create_dataset("data", data=np.array([1.0]))
            f.attrs["content_hash"] = compute_content_hash(f)

        assert verify(h5path) is True
        assert verify(h5path) is True


# ---------------------------------------------------------------------------
# Edge cases and integration
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_chunk_hash_edge_chunk(self):
        """Edge chunks (partial) should hash actual data only."""
        data = np.arange(5, dtype=np.float32)
        hasher = ChunkHasher()
        hasher.update(data)
        expected = hashlib.sha256(data.tobytes()).hexdigest()
        assert hasher.digests()[0] == expected

    def test_same_data_same_hash_different_layout(self, tmp_path: Path):
        """Same data + attrs = same hash regardless of HDF5 layout."""
        p1 = tmp_path / "a.h5"
        p2 = tmp_path / "b.h5"

        data = np.arange(24, dtype=np.float32).reshape(6, 4)

        with h5py.File(p1, "w") as f:
            f.create_dataset("d", data=data, chunks=(2, 4))
            f.attrs["name"] = "test"

        with h5py.File(p2, "w") as f:
            f.create_dataset("d", data=data, chunks=(3, 4))
            f.attrs["name"] = "test"

        with h5py.File(p1, "r") as f1, h5py.File(p2, "r") as f2:
            assert MerkleTree(f1).root_hash() == MerkleTree(f2).root_hash()

    def test_dataset_attrs_included_in_hash(self, tmp_path: Path):
        """Attributes on datasets should be included in the Merkle tree."""
        p1 = tmp_path / "a.h5"
        p2 = tmp_path / "b.h5"

        data = np.array([1.0, 2.0])

        with h5py.File(p1, "w") as f:
            ds = f.create_dataset("d", data=data)
            ds.attrs["units"] = "mm"

        with h5py.File(p2, "w") as f:
            ds = f.create_dataset("d", data=data)
            ds.attrs["units"] = "cm"

        with h5py.File(p1, "r") as f1, h5py.File(p2, "r") as f2:
            assert MerkleTree(f1).root_hash() != MerkleTree(f2).root_hash()

    def test_merkle_tree_with_chunk_hashes_present(self, h5path: Path):
        """Merkle hash should be the same whether _chunk_hashes are present or not."""
        data = np.zeros((4, 4), dtype=np.float32)

        with h5py.File(h5path, "w") as f:
            f.create_dataset("volume", data=data, chunks=(2, 4))
            f.attrs["name"] = "test"

        with h5py.File(h5path, "r") as f:
            hash_without = MerkleTree(f).root_hash()

        with h5py.File(h5path, "a") as f:
            dt = h5py.special_dtype(vlen=str)
            f.create_dataset(
                "volume_chunk_hashes",
                data=np.array(["aaa", "bbb"], dtype=object),
                dtype=dt,
            )
            f["volume_chunk_hashes"].attrs["algorithm"] = "sha256"

        with h5py.File(h5path, "r") as f:
            hash_with = MerkleTree(f).root_hash()

        assert hash_without == hash_with
