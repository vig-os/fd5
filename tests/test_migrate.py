"""Tests for fd5.migrate — migration registry and schema upgrade function."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

from fd5.hash import compute_content_hash
from fd5.schema import embed_schema


# ---------------------------------------------------------------------------
# Helpers — create a v1 fd5 file for migration tests
# ---------------------------------------------------------------------------

_V1_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "_schema_version": {"type": "integer"},
        "product": {"type": "string"},
    },
    "required": ["_schema_version", "product"],
}


def _create_v1_file(path: Path) -> Path:
    """Create a minimal v1 fd5 file with a dataset and sealed content_hash."""
    with h5py.File(path, "w") as f:
        f.attrs["product"] = "test/mock"
        f.attrs["name"] = "sample"
        f.attrs["description"] = "A v1 file"
        f.attrs["timestamp"] = "2026-01-15T10:00:00Z"
        f.attrs["id"] = "sha256:abc123"
        f.attrs["id_inputs"] = "product + name + timestamp"
        f.attrs["_schema_version"] = np.int64(1)
        embed_schema(f, _V1_SCHEMA)
        f.create_dataset("volume", data=np.zeros((4, 4), dtype=np.float32))
        f.attrs["content_hash"] = compute_content_hash(f)
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def v1_file(tmp_path: Path) -> Path:
    return _create_v1_file(tmp_path / "source_v1.h5")


@pytest.fixture()
def out_path(tmp_path: Path) -> Path:
    return tmp_path / "migrated_v2.h5"


# ---------------------------------------------------------------------------
# Import — ensures the module exists
# ---------------------------------------------------------------------------

from fd5.migrate import (  # noqa: E402
    MigrationError,
    clear_migrations,
    migrate,
    register_migration,
)


# ---------------------------------------------------------------------------
# Mock migration function: v1 → v2 for product "test/mock"
# ---------------------------------------------------------------------------


def _v1_to_v2(src: h5py.File, dst: h5py.File) -> None:
    """Mock migration: copies volume dataset, adds a new_attr."""
    if "volume" in src:
        data = src["volume"][...]
        dst.create_dataset("volume", data=data)
    dst.attrs["new_attr"] = "added_by_migration"


@pytest.fixture(autouse=True)
def _register_mock_migration():
    """Register and clean up the mock v1->v2 migration for every test."""
    register_migration("test/mock", 1, 2, _v1_to_v2)
    yield
    clear_migrations()


# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------


class TestMigrationRegistry:
    def test_register_migration_callable(self):
        clear_migrations()
        register_migration("test/mock", 1, 2, _v1_to_v2)

    def test_register_duplicate_raises(self):
        with pytest.raises(ValueError, match="already registered"):
            register_migration("test/mock", 1, 2, _v1_to_v2)

    def test_clear_migrations_allows_re_register(self):
        clear_migrations()
        register_migration("test/mock", 1, 2, _v1_to_v2)


# ---------------------------------------------------------------------------
# migrate() — happy path
# ---------------------------------------------------------------------------


class TestMigrateHappyPath:
    def test_creates_output_file(self, v1_file: Path, out_path: Path):
        migrate(v1_file, out_path, target_version=2)
        assert out_path.exists()

    def test_output_has_upgraded_schema_version(self, v1_file: Path, out_path: Path):
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            assert int(f.attrs["_schema_version"]) == 2

    def test_output_preserves_product(self, v1_file: Path, out_path: Path):
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            product = f.attrs["product"]
            if isinstance(product, bytes):
                product = product.decode()
            assert product == "test/mock"

    def test_output_preserves_existing_attrs(self, v1_file: Path, out_path: Path):
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            name = f.attrs["name"]
            if isinstance(name, bytes):
                name = name.decode()
            assert name == "sample"

    def test_migration_callable_applied(self, v1_file: Path, out_path: Path):
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            val = f.attrs["new_attr"]
            if isinstance(val, bytes):
                val = val.decode()
            assert val == "added_by_migration"

    def test_dataset_copied(self, v1_file: Path, out_path: Path):
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            assert "volume" in f
            assert f["volume"].shape == (4, 4)

    def test_content_hash_recomputed(self, v1_file: Path, out_path: Path):
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            stored = f.attrs["content_hash"]
            if isinstance(stored, bytes):
                stored = stored.decode()
            assert stored.startswith("sha256:")
            recomputed = compute_content_hash(f)
            assert stored == recomputed

    def test_content_hash_differs_from_source(self, v1_file: Path, out_path: Path):
        with h5py.File(v1_file, "r") as f:
            old_hash = f.attrs["content_hash"]
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            new_hash = f.attrs["content_hash"]
        assert old_hash != new_hash


# ---------------------------------------------------------------------------
# Provenance chain — migrated file links to original
# ---------------------------------------------------------------------------


class TestProvenanceChain:
    def test_sources_group_exists(self, v1_file: Path, out_path: Path):
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            assert "sources" in f

    def test_source_references_original_file(self, v1_file: Path, out_path: Path):
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            src_grp = f["sources/migrated_from"]
            file_attr = src_grp.attrs["file"]
            if isinstance(file_attr, bytes):
                file_attr = file_attr.decode()
            assert file_attr == str(v1_file)

    def test_source_has_original_content_hash(self, v1_file: Path, out_path: Path):
        with h5py.File(v1_file, "r") as f:
            original_hash = f.attrs["content_hash"]
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            src_grp = f["sources/migrated_from"]
            stored_hash = src_grp.attrs["content_hash"]
            if isinstance(stored_hash, bytes):
                stored_hash = stored_hash.decode()
            if isinstance(original_hash, bytes):
                original_hash = original_hash.decode()
            assert stored_hash == original_hash

    def test_source_role_is_migration_source(self, v1_file: Path, out_path: Path):
        migrate(v1_file, out_path, target_version=2)
        with h5py.File(out_path, "r") as f:
            role = f["sources/migrated_from"].attrs["role"]
            if isinstance(role, bytes):
                role = role.decode()
            assert role == "migration_source"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestMigrateErrors:
    def test_source_file_not_found(self, tmp_path: Path, out_path: Path):
        with pytest.raises(FileNotFoundError):
            migrate(tmp_path / "nonexistent.h5", out_path, target_version=2)

    def test_no_migration_registered(self, v1_file: Path, out_path: Path):
        clear_migrations()
        with pytest.raises(MigrationError, match="No migration"):
            migrate(v1_file, out_path, target_version=2)

    def test_already_at_target_version(self, v1_file: Path, out_path: Path):
        with pytest.raises(MigrationError, match="already at"):
            migrate(v1_file, out_path, target_version=1)

    def test_target_below_current_version(self, v1_file: Path, out_path: Path):
        with pytest.raises(MigrationError, match="already at"):
            migrate(v1_file, out_path, target_version=0)


# ---------------------------------------------------------------------------
# Multi-step migration (v1 -> v2 -> v3)
# ---------------------------------------------------------------------------


def _v2_to_v3(src: h5py.File, dst: h5py.File) -> None:
    """Mock migration: copies volume, copies new_attr, adds another_attr."""
    if "volume" in src:
        dst.create_dataset("volume", data=src["volume"][...])
    new_attr = src.attrs.get("new_attr", "")
    if new_attr:
        dst.attrs["new_attr"] = new_attr
    dst.attrs["another_attr"] = "v3_addition"


class TestMultiStepMigration:
    def test_chain_v1_to_v3(self, v1_file: Path, tmp_path: Path):
        register_migration("test/mock", 2, 3, _v2_to_v3)
        out = tmp_path / "migrated_v3.h5"
        migrate(v1_file, out, target_version=3)
        with h5py.File(out, "r") as f:
            assert int(f.attrs["_schema_version"]) == 3
            val = f.attrs["another_attr"]
            if isinstance(val, bytes):
                val = val.decode()
            assert val == "v3_addition"
