"""fd5.ingest._base — Loader protocol and shared ingest helpers.

Defines the interface all format-specific loaders must implement and
provides utility functions for source-file hashing and loader discovery.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fd5._types import Fd5Path

_READ_CHUNK = 1024 * 1024  # 1 MiB

_EP_GROUP = "fd5.loaders"


@runtime_checkable
class Loader(Protocol):
    """Protocol that all fd5 ingest loaders must satisfy."""

    @property
    def supported_product_types(self) -> list[str]:
        """Product types this loader can produce (e.g. ``['recon', 'listmode']``)."""
        ...

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
        """Read source data and produce a sealed fd5 file."""
        ...


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def hash_source_files(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Hash source files for ``provenance/original_files`` records.

    Returns a list of dicts with keys ``path``, ``sha256``, and
    ``size_bytes`` — matching the schema expected by
    :func:`fd5.provenance.write_original_files`.
    """
    records: list[dict[str, Any]] = []
    for p in paths:
        p = Path(p)
        h = hashlib.sha256()
        size = 0
        with p.open("rb") as fh:
            while chunk := fh.read(_READ_CHUNK):
                h.update(chunk)
                size += len(chunk)
        records.append(
            {
                "path": str(p),
                "sha256": f"sha256:{h.hexdigest()}",
                "size_bytes": size,
            }
        )
    return records


def _load_loader_entry_points() -> dict[str, Any]:
    """Load callables from the ``fd5.loaders`` entry-point group."""
    factories: dict[str, Any] = {}
    for ep in importlib.metadata.entry_points(group=_EP_GROUP):
        factories[ep.name] = ep.load()
    return factories


def discover_loaders() -> dict[str, Loader]:
    """Discover available loaders based on installed optional deps.

    Iterates over entry points in the ``fd5.loaders`` group.  Each entry
    point should be a callable returning a :class:`Loader` instance.
    Loaders whose dependencies are missing (``ImportError``) are silently
    skipped.
    """
    factories = _load_loader_entry_points()
    loaders: dict[str, Loader] = {}
    for name, factory in factories.items():
        try:
            loader = factory()
        except ImportError:
            continue
        if isinstance(loader, Loader):
            loaders[name] = loader
    return loaders
