"""fd5.ingest._base — Loader protocol and shared ingest helpers.

Defines the structural interface all format-specific loaders must satisfy
and provides utilities for source file hashing (provenance tracking).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, runtime_checkable

from fd5._types import Fd5Path

_HASH_BUF_SIZE = 1 << 16  # 64 KiB


@runtime_checkable
class Loader(Protocol):
    """Protocol that all fd5 ingest loaders must satisfy."""

    @property
    def supported_product_types(self) -> list[str]:
        """Product types this loader can produce."""
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
        **kwargs: object,
    ) -> Fd5Path:
        """Read source data and produce a sealed fd5 file."""
        ...


def hash_source_files(paths: Iterable[Path]) -> list[dict[str, str | int]]:
    """Compute SHA-256 and file size for each path.

    Returns a list of dicts suitable for
    :func:`fd5.provenance.write_original_files`.

    Raises:
        FileNotFoundError: If any path does not exist.
    """
    records: list[dict[str, str | int]] = []
    for p in paths:
        p = Path(p)
        sha = hashlib.sha256()
        with p.open("rb") as fh:
            while chunk := fh.read(_HASH_BUF_SIZE):
                sha.update(chunk)
        records.append(
            {
                "path": str(p),
                "sha256": sha.hexdigest(),
                "size_bytes": p.stat().st_size,
            }
        )
    return records
