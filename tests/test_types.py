"""Tests for fd5._types — shared types module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fd5._types import ContentHash, Fd5Path, ProductSchema, SourceRecord


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------


class TestTypeAliases:
    """Fd5Path and ContentHash are transparent aliases."""

    def test_fd5path_is_pathlib_path(self):
        assert Fd5Path is Path

    def test_content_hash_is_str(self):
        assert ContentHash is str


# ---------------------------------------------------------------------------
# ProductSchema protocol
# ---------------------------------------------------------------------------


class _StubSchema:
    """Minimal implementation satisfying the ProductSchema protocol."""

    product_type: str = "test/stub"
    schema_version: str = "1.0.0"

    def json_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    def required_root_attrs(self) -> dict[str, Any]:
        return {"product_type": "test/stub"}

    def write(self, target: Any, data: Any) -> None:
        pass

    def id_inputs(self) -> list[str]:
        return ["/scan/start_time"]


class TestProductSchemaProtocol:
    """ProductSchema protocol imported from _types behaves correctly."""

    def test_stub_is_instance(self):
        assert isinstance(_StubSchema(), ProductSchema)

    def test_plain_object_is_not_instance(self):
        assert not isinstance(object(), ProductSchema)

    def test_reexported_from_registry(self):
        from fd5.registry import ProductSchema as RegistrySchema

        assert RegistrySchema is ProductSchema


# ---------------------------------------------------------------------------
# SourceRecord
# ---------------------------------------------------------------------------


class TestSourceRecord:
    """SourceRecord dataclass creation and behaviour."""

    def _make(self, **overrides: Any) -> SourceRecord:
        defaults: dict[str, str] = {
            "path": "/data/raw/scan.h5",
            "content_hash": "sha256:abc123",
            "product_type": "listmode",
            "id": "sha256:def456",
        }
        defaults.update(overrides)
        return SourceRecord(**defaults)

    def test_fields(self):
        rec = self._make()
        assert rec.path == "/data/raw/scan.h5"
        assert rec.content_hash == "sha256:abc123"
        assert rec.product_type == "listmode"
        assert rec.id == "sha256:def456"

    def test_frozen(self):
        rec = self._make()
        with pytest.raises(AttributeError):
            rec.path = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        rec = self._make()
        d = rec.to_dict()
        assert isinstance(d, dict)
        assert d == {
            "path": "/data/raw/scan.h5",
            "content_hash": "sha256:abc123",
            "product_type": "listmode",
            "id": "sha256:def456",
        }

    def test_equality(self):
        a = self._make()
        b = self._make()
        assert a == b

    def test_inequality_on_different_field(self):
        a = self._make(path="/a")
        b = self._make(path="/b")
        assert a != b

    def test_hashable(self):
        rec = self._make()
        assert hash(rec) == hash(self._make())
        assert {rec} == {self._make()}
