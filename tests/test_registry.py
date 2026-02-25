"""Tests for fd5.registry – product schema registry."""

from __future__ import annotations

from typing import Any

import pytest

from fd5.registry import (
    ProductSchema,
    get_schema,
    list_schemas,
    register_schema,
)


class _StubSchema:
    """Minimal implementation satisfying the ProductSchema protocol."""

    product_type: str = "test.stub"
    schema_version: str = "1.0.0"

    def json_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    def required_root_attrs(self) -> dict[str, Any]:
        return {"product_type": self.product_type}

    def write(self, path: Any, data: Any) -> None:  # noqa: ARG002
        pass

    def id_inputs(self) -> list[str]:
        return ["product_type"]


class TestProductSchemaProtocol:
    """ProductSchema is a structural (Protocol) type."""

    def test_stub_satisfies_protocol(self) -> None:
        schema: ProductSchema = _StubSchema()
        assert schema.product_type == "test.stub"

    def test_protocol_has_required_attributes(self) -> None:
        schema = _StubSchema()
        assert hasattr(schema, "product_type")
        assert hasattr(schema, "schema_version")
        assert callable(schema.json_schema)
        assert callable(schema.required_root_attrs)
        assert callable(schema.write)
        assert callable(schema.id_inputs)


class TestRegisterSchema:
    """register_schema() allows dynamic registration."""

    def test_register_and_retrieve(self) -> None:
        stub = _StubSchema()
        register_schema("test.register", stub)
        assert get_schema("test.register") is stub

    def test_register_overwrites_existing(self) -> None:
        stub_a = _StubSchema()
        stub_b = _StubSchema()
        register_schema("test.overwrite", stub_a)
        register_schema("test.overwrite", stub_b)
        assert get_schema("test.overwrite") is stub_b


class TestGetSchema:
    """get_schema() returns a registered schema or raises ValueError."""

    def test_raises_for_unknown_product_type(self) -> None:
        with pytest.raises(ValueError, match="no_such_product"):
            get_schema("no_such_product")

    def test_returns_registered_schema(self) -> None:
        stub = _StubSchema()
        register_schema("test.get", stub)
        assert get_schema("test.get") is stub


class TestListSchemas:
    """list_schemas() returns all registered product type strings."""

    def test_includes_registered_types(self) -> None:
        stub = _StubSchema()
        register_schema("test.list_a", stub)
        register_schema("test.list_b", stub)
        result = list_schemas()
        assert "test.list_a" in result
        assert "test.list_b" in result

    def test_returns_list_of_strings(self) -> None:
        result = list_schemas()
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)


class TestEntryPointDiscovery:
    """Entry points in the fd5.schemas group are loaded on first access."""

    def test_entry_point_group_is_fd5_schemas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify discovery uses the correct entry point group."""
        import fd5.registry as reg

        calls: list[str] = []

        class _FakeEntryPoint:
            name = "test.ep"

            def load(self) -> type:
                return _StubSchema

        def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
            calls.append(group)
            return [_FakeEntryPoint()]

        reg._registry.clear()
        reg._discovered = False
        monkeypatch.setattr("fd5.registry._load_entry_points", fake_entry_points)
        list_schemas()
        assert calls == ["fd5.schemas"]

    def test_entry_point_schema_is_instantiated_and_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import fd5.registry as reg

        class _FakeEntryPoint:
            name = "test.ep_inst"

            def load(self) -> type:
                return _StubSchema

        def fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:  # noqa: ARG001
            return [_FakeEntryPoint()]

        reg._registry.clear()
        reg._discovered = False
        monkeypatch.setattr("fd5.registry._load_entry_points", fake_entry_points)
        schema = get_schema("test.ep_inst")
        assert isinstance(schema, _StubSchema)
