"""Tests for fd5.schema — embed, validate, dump, and generate JSON Schema."""

from __future__ import annotations

import json
from typing import Any

import h5py
import pytest

from fd5.registry import register_schema
from fd5.schema import dump_schema, embed_schema, generate_schema, validate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubSchema:
    """Minimal ProductSchema for testing."""

    product_type: str = "test/schema"
    schema_version: str = "1.0.0"

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "test/schema"},
                "name": {"type": "string"},
            },
            "required": ["_schema_version", "product", "name"],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {"product": "test/schema"}

    def write(self, target: Any, data: Any) -> None:
        pass

    def id_inputs(self) -> list[str]:
        return ["/name"]


@pytest.fixture()
def h5file(tmp_path):
    """Yield a writable HDF5 file, auto-closed after test."""
    path = tmp_path / "test.h5"
    with h5py.File(path, "w") as f:
        yield f


@pytest.fixture()
def h5path(tmp_path):
    """Return a path for an HDF5 file (closed between write and read)."""
    return tmp_path / "test.h5"


@pytest.fixture(autouse=True)
def _register_stub():
    """Register the stub schema for every test."""
    register_schema("test/schema", _StubSchema())


# ---------------------------------------------------------------------------
# embed_schema
# ---------------------------------------------------------------------------


class TestEmbedSchema:
    def test_writes_schema_attr_as_json_string(self, h5file):
        schema_dict = {"type": "object", "properties": {}}
        embed_schema(h5file, schema_dict)
        raw = h5file.attrs["_schema"]
        assert isinstance(raw, str)
        assert json.loads(raw) == schema_dict

    def test_writes_schema_version_as_int(self, h5file):
        embed_schema(h5file, {"type": "object"}, schema_version=2)
        assert h5file.attrs["_schema_version"] == 2

    def test_default_schema_version_is_one(self, h5file):
        embed_schema(h5file, {"type": "object"})
        assert h5file.attrs["_schema_version"] == 1

    def test_schema_readable_by_h5_tools(self, h5path):
        """Schema stored as plain JSON string is human-readable via h5dump."""
        schema_dict = {"type": "object", "description": "test"}
        with h5py.File(h5path, "w") as f:
            embed_schema(f, schema_dict)
        with h5py.File(h5path, "r") as f:
            raw = f.attrs["_schema"]
            parsed = json.loads(raw)
            assert parsed == schema_dict

    def test_idempotent_overwrites(self, h5file):
        embed_schema(h5file, {"v": 1})
        embed_schema(h5file, {"v": 2}, schema_version=3)
        assert json.loads(h5file.attrs["_schema"]) == {"v": 2}
        assert h5file.attrs["_schema_version"] == 3


# ---------------------------------------------------------------------------
# dump_schema
# ---------------------------------------------------------------------------


class TestDumpSchema:
    def test_extracts_embedded_schema(self, h5path):
        schema_dict = {"type": "object", "properties": {"x": {"type": "integer"}}}
        with h5py.File(h5path, "w") as f:
            embed_schema(f, schema_dict)
        result = dump_schema(h5path)
        assert result == schema_dict

    def test_raises_on_missing_schema(self, h5path):
        with h5py.File(h5path, "w") as f:
            f.attrs["other"] = "value"
        with pytest.raises(KeyError, match="_schema"):
            dump_schema(h5path)

    def test_raises_on_invalid_json(self, h5path):
        with h5py.File(h5path, "w") as f:
            f.attrs["_schema"] = "not valid json {"
        with pytest.raises(json.JSONDecodeError):
            dump_schema(h5path)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


class TestValidate:
    def _make_valid_file(self, path):
        schema_dict = _StubSchema().json_schema()
        with h5py.File(path, "w") as f:
            embed_schema(f, schema_dict)
            f.attrs["product"] = "test/schema"
            f.attrs["name"] = "sample"

    def test_valid_file_returns_empty_list(self, h5path):
        self._make_valid_file(h5path)
        errors = validate(h5path)
        assert errors == []

    def test_missing_required_attr_returns_errors(self, h5path):
        schema_dict = _StubSchema().json_schema()
        with h5py.File(h5path, "w") as f:
            embed_schema(f, schema_dict)
            f.attrs["product"] = "test/schema"
            # 'name' is missing
        errors = validate(h5path)
        assert len(errors) > 0
        messages = [e.message for e in errors]
        assert any("name" in m for m in messages)

    def test_wrong_type_returns_errors(self, h5path):
        schema_dict = _StubSchema().json_schema()
        with h5py.File(h5path, "w") as f:
            embed_schema(f, schema_dict)
            f.attrs["product"] = "test/schema"
            f.attrs["name"] = "sample"
            f.attrs["_schema_version"] = "not_an_int"
        errors = validate(h5path)
        assert len(errors) > 0

    def test_raises_when_no_schema_embedded(self, h5path):
        with h5py.File(h5path, "w") as f:
            f.attrs["product"] = "test/schema"
        with pytest.raises(KeyError, match="_schema"):
            validate(h5path)

    def test_const_violation_returns_errors(self, h5path):
        schema_dict = _StubSchema().json_schema()
        with h5py.File(h5path, "w") as f:
            embed_schema(f, schema_dict)
            f.attrs["product"] = "wrong/type"
            f.attrs["name"] = "sample"
        errors = validate(h5path)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# generate_schema
# ---------------------------------------------------------------------------


class TestGenerateSchema:
    def test_returns_json_schema_draft_2020_12(self):
        result = generate_schema("test/schema")
        assert result["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_returns_dict_from_registry(self):
        result = generate_schema("test/schema")
        assert result["type"] == "object"
        assert "properties" in result

    def test_unknown_product_raises_valueerror(self):
        with pytest.raises(ValueError, match="no-such-type"):
            generate_schema("no-such-type")
