"""Product schema registry with entry-point discovery.

Discovers product schemas from ``importlib.metadata`` entry points
(group ``fd5.schemas``), allows lookup by product-type string, and
provides a ``register_schema`` escape-hatch for testing.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProductSchema(Protocol):
    """Structural interface every product schema must satisfy."""

    product_type: str
    schema_version: str

    def json_schema(self) -> dict[str, Any]: ...
    def required_root_attrs(self) -> dict[str, Any]: ...
    def write(self, target: Any, data: Any) -> None: ...
    def id_inputs(self) -> list[str]: ...


_registry: dict[str, ProductSchema] = {}
_ep_loaded: bool = False

_EP_GROUP = "fd5.schemas"


def _load_entry_points() -> dict[str, ProductSchema]:
    """Load all entry points in the ``fd5.schemas`` group.

    Each entry point must be a callable returning a ``ProductSchema``
    instance.  The entry-point *name* is used as the product-type key.
    """
    schemas: dict[str, ProductSchema] = {}
    for ep in importlib.metadata.entry_points(group=_EP_GROUP):
        factory = ep.load()
        schemas[ep.name] = factory()
    return schemas


def _load_and_merge() -> None:
    """Merge entry-point schemas into the registry (once)."""
    global _ep_loaded  # noqa: PLW0603
    ep_schemas = _load_entry_points()
    for name, schema in ep_schemas.items():
        _registry.setdefault(name, schema)
    _ep_loaded = True


def _ensure_loaded() -> None:
    if not _ep_loaded:
        _load_and_merge()


def register_schema(product_type: str, schema: ProductSchema) -> None:
    """Register *schema* under *product_type* (overwrites existing)."""
    _registry[product_type] = schema


def get_schema(product_type: str) -> ProductSchema:
    """Return the schema registered for *product_type*.

    Raises:
        ValueError: If no schema is registered for *product_type*.
    """
    _ensure_loaded()
    try:
        return _registry[product_type]
    except KeyError:
        raise ValueError(
            f"No schema registered for product type {product_type!r}"
        ) from None


def list_schemas() -> list[str]:
    """Return all registered product-type strings."""
    _ensure_loaded()
    return list(_registry)
