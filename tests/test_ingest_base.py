"""Tests for fd5.ingest._base module."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from fd5.ingest._base import Loader, hash_source_files


class TestLoaderProtocol:
    """Loader is a runtime-checkable Protocol."""

    def test_protocol_is_runtime_checkable(self):
        assert hasattr(Loader, "__protocol_attrs__")

    def test_conforming_class_is_instance(self):
        class _Good:
            @property
            def supported_product_types(self) -> list[str]:
                return ["recon"]

            def ingest(
                self,
                source,
                output_dir,
                *,
                product,
                name,
                description,
                timestamp=None,
                **kwargs,
            ):
                return Path("out.h5")

        assert isinstance(_Good(), Loader)

    def test_non_conforming_class_is_not_instance(self):
        class _Bad:
            pass

        assert not isinstance(_Bad(), Loader)


class TestHashSourceFiles:
    """Tests for hash_source_files()."""

    def test_single_file(self, tmp_path: Path):
        f = tmp_path / "data.bin"
        content = b"hello world"
        f.write_bytes(content)

        result = hash_source_files([f])
        assert len(result) == 1
        rec = result[0]
        assert rec["path"] == str(f)
        assert rec["sha256"] == hashlib.sha256(content).hexdigest()
        assert rec["size_bytes"] == len(content)

    def test_multiple_files(self, tmp_path: Path):
        files = []
        for i in range(3):
            p = tmp_path / f"file_{i}.bin"
            p.write_bytes(bytes([i]) * (i + 1))
            files.append(p)

        result = hash_source_files(files)
        assert len(result) == 3
        for i, rec in enumerate(result):
            assert rec["size_bytes"] == i + 1

    def test_empty_iterable(self):
        assert hash_source_files([]) == []

    def test_nonexistent_file_raises(self, tmp_path: Path):
        missing = tmp_path / "no_such_file.bin"
        with pytest.raises(FileNotFoundError):
            hash_source_files([missing])

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")

        result = hash_source_files([f])
        assert result[0]["size_bytes"] == 0
        assert result[0]["sha256"] == hashlib.sha256(b"").hexdigest()

    def test_large_file_crosses_buffer_boundary(self, tmp_path: Path):
        f = tmp_path / "large.bin"
        content = b"x" * (1 << 17)  # 128 KiB > 64 KiB buffer
        f.write_bytes(content)

        result = hash_source_files([f])
        assert result[0]["sha256"] == hashlib.sha256(content).hexdigest()
