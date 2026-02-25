"""Shared types for the fd5 package.

Centralises protocols, dataclasses, and type aliases so that other
modules can import lightweight types without pulling in heavy
dependencies.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Fd5Path = Path
"""Alias for ``pathlib.Path`` — semantic hint for fd5-related file paths."""

ContentHash = str
"""Alias for ``str`` — a content-addressable hash (e.g. ``sha256:…``)."""

# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class ProductSchema(Protocol):
    """Structural interface every product schema must satisfy."""

    product_type: str
    schema_version: str

    def json_schema(self) -> dict[str, Any]: ...
    def required_root_attrs(self) -> dict[str, Any]: ...
    def write(self, target: Any, data: Any) -> None: ...
    def id_inputs(self) -> list[str]: ...


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class SourceRecord:
    """Immutable record describing a source data product.

    Fields mirror the minimum metadata needed to track a source in the
    provenance DAG.
    """

    path: str
    content_hash: ContentHash
    product_type: str
    id: str

    def to_dict(self) -> dict[str, str]:
        """Return a plain ``dict`` representation."""
        return dataclasses.asdict(self)
