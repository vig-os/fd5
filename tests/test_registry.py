"""Tests for fd5.registry module."""

from __future__ import annotations

from typing import Any

import pytest

from fd5.registry import ProductSchema, get_schema, list_schemas, register_schema


class _StubSchema:
    """Minimal implementation satisfying the ProductSchema protocol."""

    product_type: str = "pet/static"
    schema_version: str = "1.0.0"

    def json_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    def required_root_attrs(self) -> dict[str, Any]:
        return {"product_type": "pet/static"}

    def write(self, target: Any, data: Any) -> None:
        pass

    def id_inputs(self) -> list[str]:
        return ["/scan/start_time"]


def _assert_satisfies_protocol(obj: object) -> None:
    """Verify *obj* is structurally compatible with ProductSchema."""
    schema: ProductSchema = obj  # type: ignore[assignment]
    assert hasattr(schema, "product_type")
    assert hasattr(schema, "schema_version")
    assert callable(schema.json_schema)
    assert callable(schema.required_root_attrs)
    assert callable(schema.write)
    assert callable(schema.id_inputs)


class TestProductSchemaProtocol:
    """ProductSchema is a typing.Protocol — verify structural subtyping."""

    def test_stub_satisfies_protocol(self):
        _assert_satisfies_protocol(_StubSchema())

    def test_protocol_has_required_members(self):
        import inspect

        methods = {
            name
            for name, _ in inspect.getmembers(ProductSchema)
            if not name.startswith("_")
        }
        annotations = set(ProductSchema.__protocol_attrs__)
        all_members = methods | annotations
        assert all_members >= {
            "product_type",
            "schema_version",
            "json_schema",
            "required_root_attrs",
            "write",
            "id_inputs",
        }


class TestRegisterSchema:
    """Tests for register_schema."""

    def test_registers_and_retrieves(self):
        stub = _StubSchema()
        register_schema("test/register", stub)
        assert get_schema("test/register") is stub

    def test_overwrites_existing(self):
        stub_a = _StubSchema()
        stub_b = _StubSchema()
        register_schema("test/overwrite", stub_a)
        register_schema("test/overwrite", stub_b)
        assert get_schema("test/overwrite") is stub_b

    def test_appears_in_list(self):
        stub = _StubSchema()
        register_schema("test/listed", stub)
        assert "test/listed" in list_schemas()


class TestGetSchema:
    """Tests for get_schema."""

    def test_returns_registered_schema(self):
        stub = _StubSchema()
        register_schema("test/get", stub)
        assert get_schema("test/get") is stub

    def test_unknown_product_type_raises_valueerror(self):
        with pytest.raises(ValueError, match="no-such-product"):
            get_schema("no-such-product")


class TestListSchemas:
    """Tests for list_schemas."""

    def test_returns_list_of_strings(self):
        result = list_schemas()
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_contains_registered_types(self):
        register_schema("test/list-a", _StubSchema())
        register_schema("test/list-b", _StubSchema())
        result = list_schemas()
        assert "test/list-a" in result
        assert "test/list-b" in result


class TestEntryPointDiscovery:
    """Entry point loading uses importlib.metadata group 'fd5.schemas'."""

    def test_loads_entry_points_on_first_access(self, monkeypatch):
        """Schemas from entry points are available via get_schema."""
        import fd5.registry as reg

        stub = _StubSchema()
        stub.product_type = "ep/test"

        class FakeEntryPoint:
            name = "ep/test"

            def load(self):
                return lambda: stub

        monkeypatch.setattr(
            reg,
            "_load_entry_points",
            lambda: {"ep/test": stub},
        )
        reg._registry.clear()
        reg._load_and_merge()

        assert get_schema("ep/test") is stub
