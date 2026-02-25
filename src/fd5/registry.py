"""Product schema registry with entry-point discovery.

Schemas are discovered from the ``fd5.schemas`` entry-point group
(importlib.metadata) on first access.  `register_schema` provides a
manual escape hatch for testing or ad-hoc registration.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProductSchema(Protocol):
    """Structural interface every product schema must satisfy."""

    product_type: str
    schema_version: str

    def json_schema(self) -> dict[str, Any]: ...
    def required_root_attrs(self) -> dict[str, Any]: ...
    def write(self, path: Any, data: Any) -> None: ...
    def id_inputs(self) -> list[str]: ...


_registry: dict[str, ProductSchema] = {}
_discovered: bool = False

_load_entry_points = entry_points


def _ensure_discovered() -> None:
    """Load entry points from the ``fd5.schemas`` group exactly once."""
    global _discovered  # noqa: PLW0603
    if _discovered:
        return
    _discovered = True
    for ep in _load_entry_points(group="fd5.schemas"):
        schema_cls = ep.load()
        instance = schema_cls()
        _registry.setdefault(ep.name, instance)


def get_schema(product_type: str) -> ProductSchema:
    """Return the schema registered for *product_type*, or raise ``ValueError``."""
    _ensure_discovered()
    try:
        return _registry[product_type]
    except KeyError:
        raise ValueError(
            f"No schema registered for product type {product_type!r}"
        ) from None


def list_schemas() -> list[str]:
    """Return all registered product-type strings."""
    _ensure_discovered()
    return list(_registry.keys())


def register_schema(product_type: str, schema: ProductSchema) -> None:
    """Register *schema* under *product_type* (useful for testing)."""
    _registry[product_type] = schema
