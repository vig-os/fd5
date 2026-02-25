"""Tests for fd5.ingest._base — Loader protocol and shared helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from fd5._types import Fd5Path
from fd5.ingest._base import (
    Loader,
    _load_loader_entry_points,
    discover_loaders,
    hash_source_files,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _ValidLoader:
    """Minimal concrete class satisfying the Loader protocol."""

    @property
    def supported_product_types(self) -> list[str]:
        return ["recon"]

    def ingest(
        self,
        source: Path | str,
        output_dir: Path,
        *,
        product: str,
        name: str,
        description: str,
        timestamp: str | None = None,
        **kwargs: Any,
    ) -> Fd5Path:
        return output_dir / "out.h5"


class _MissingIngest:
    """Has supported_product_types but no ingest method."""

    @property
    def supported_product_types(self) -> list[str]:
        return ["recon"]


class _MissingProductTypes:
    """Has ingest but no supported_product_types."""

    def ingest(
        self,
        source: Path | str,
        output_dir: Path,
        *,
        product: str,
        name: str,
        description: str,
        timestamp: str | None = None,
        **kwargs: Any,
    ) -> Fd5Path:
        return output_dir / "out.h5"


# ---------------------------------------------------------------------------
# Loader protocol
# ---------------------------------------------------------------------------


class TestLoaderProtocol:
    """Loader is a runtime_checkable Protocol."""

    def test_valid_loader_is_instance(self):
        assert isinstance(_ValidLoader(), Loader)

    def test_missing_ingest_not_instance(self):
        assert not isinstance(_MissingIngest(), Loader)

    def test_missing_product_types_not_instance(self):
        assert not isinstance(_MissingProductTypes(), Loader)

    def test_protocol_requires_supported_product_types(self):
        import inspect

        members = {
            name for name, _ in inspect.getmembers(Loader) if not name.startswith("_")
        }
        attrs = set(Loader.__protocol_attrs__)
        assert (members | attrs) >= {"supported_product_types", "ingest"}

    def test_plain_object_not_instance(self):
        assert not isinstance(object(), Loader)


# ---------------------------------------------------------------------------
# hash_source_files
# ---------------------------------------------------------------------------


class TestHashSourceFiles:
    """hash_source_files computes SHA-256 + size for provenance records."""

    def test_single_file(self, tmp_path: Path):
        p = tmp_path / "data.bin"
        content = b"hello world"
        p.write_bytes(content)

        result = hash_source_files([p])

        assert len(result) == 1
        rec = result[0]
        assert rec["path"] == str(p)
        assert rec["sha256"] == f"sha256:{hashlib.sha256(content).hexdigest()}"
        assert rec["size_bytes"] == len(content)

    def test_multiple_files(self, tmp_path: Path):
        paths = []
        for i in range(3):
            p = tmp_path / f"file_{i}.dat"
            p.write_bytes(f"content-{i}".encode())
            paths.append(p)

        result = hash_source_files(paths)
        assert len(result) == 3
        assert all(r["sha256"].startswith("sha256:") for r in result)

    def test_empty_iterable(self):
        result = hash_source_files([])
        assert result == []

    def test_large_file_chunked(self, tmp_path: Path):
        """Hash must be correct even for files larger than a typical read buffer."""
        p = tmp_path / "large.bin"
        data = b"x" * (2 * 1024 * 1024)
        p.write_bytes(data)

        result = hash_source_files([p])
        expected = f"sha256:{hashlib.sha256(data).hexdigest()}"
        assert result[0]["sha256"] == expected

    def test_record_keys(self, tmp_path: Path):
        p = tmp_path / "keys.bin"
        p.write_bytes(b"abc")

        rec = hash_source_files([p])[0]
        assert set(rec.keys()) == {"path", "sha256", "size_bytes"}

    def test_size_bytes_is_int(self, tmp_path: Path):
        p = tmp_path / "sz.bin"
        p.write_bytes(b"12345")

        rec = hash_source_files([p])[0]
        assert isinstance(rec["size_bytes"], int)

    def test_nonexistent_file_raises(self, tmp_path: Path):
        missing = tmp_path / "no_such_file.bin"
        with pytest.raises((FileNotFoundError, OSError)):
            hash_source_files([missing])


# ---------------------------------------------------------------------------
# discover_loaders
# ---------------------------------------------------------------------------


class TestDiscoverLoaders:
    """discover_loaders returns loaders whose optional deps are installed."""

    def test_returns_dict(self):
        result = discover_loaders()
        assert isinstance(result, dict)

    def test_values_satisfy_protocol(self):
        for loader in discover_loaders().values():
            assert isinstance(loader, Loader)

    def test_keys_are_strings(self):
        for key in discover_loaders():
            assert isinstance(key, str)

    def test_no_loaders_when_entry_points_empty(self, monkeypatch):
        import fd5.ingest._base as base_mod

        monkeypatch.setattr(
            base_mod,
            "_load_loader_entry_points",
            lambda: {},
        )
        result = discover_loaders()
        assert result == {}

    def test_loader_with_missing_deps_excluded(self, monkeypatch):
        """If a loader's entry point raises ImportError, it is skipped."""
        import fd5.ingest._base as base_mod

        def _fake_load():
            raise ImportError("numpy not installed")

        def _fake_eps():
            return {"broken": _fake_load}

        monkeypatch.setattr(base_mod, "_load_loader_entry_points", _fake_eps)
        result = discover_loaders()
        assert "broken" not in result

    def test_valid_loader_discovered(self, monkeypatch):
        """A factory returning a valid Loader is included in the result."""
        import fd5.ingest._base as base_mod

        monkeypatch.setattr(
            base_mod,
            "_load_loader_entry_points",
            lambda: {"good": _ValidLoader},
        )
        result = discover_loaders()
        assert "good" in result
        assert isinstance(result["good"], Loader)

    def test_non_loader_object_excluded(self, monkeypatch):
        """If a factory returns something that isn't a Loader, skip it."""
        import fd5.ingest._base as base_mod

        monkeypatch.setattr(
            base_mod,
            "_load_loader_entry_points",
            lambda: {"bad": lambda: object()},
        )
        result = discover_loaders()
        assert "bad" not in result


class TestLoadLoaderEntryPoints:
    """_load_loader_entry_points reads the fd5.loaders entry-point group."""

    def test_returns_dict(self):
        result = _load_loader_entry_points()
        assert isinstance(result, dict)

    def test_loads_entry_point_callables(self, monkeypatch):
        """Each entry point's .load() result is stored by name."""
        import importlib.metadata
        from unittest.mock import MagicMock

        ep = MagicMock()
        ep.name = "mock_loader"
        ep.load.return_value = _ValidLoader

        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda group: [ep] if group == "fd5.loaders" else [],
        )
        result = _load_loader_entry_points()
        assert "mock_loader" in result
        assert result["mock_loader"] is _ValidLoader
