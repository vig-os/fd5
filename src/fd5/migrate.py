"""fd5.migrate — schema version migration for fd5 files.

Copy-on-write migration: reads a source fd5 file, applies registered
migration callables to produce a new file at the target schema version,
records provenance linking the new file to the original, and recomputes
the content_hash.

See white-paper.md § Versioning / Migration and upgrades.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

import h5py
import numpy as np

from fd5.hash import compute_content_hash
from fd5.provenance import write_sources


class MigrationError(Exception):
    """Raised when a migration cannot be performed."""


MigrationCallable = Callable[[h5py.File, h5py.File], None]

_registry: dict[tuple[str, int, int], MigrationCallable] = {}


def register_migration(
    product: str,
    from_version: int,
    to_version: int,
    fn: MigrationCallable,
) -> None:
    """Register a migration callable for *product* from *from_version* to *to_version*.

    Raises ``ValueError`` if a migration for the same key is already registered.
    """
    key = (product, from_version, to_version)
    if key in _registry:
        raise ValueError(
            f"Migration already registered for {product!r} "
            f"v{from_version} -> v{to_version}"
        )
    _registry[key] = fn


def clear_migrations() -> None:
    """Remove all registered migrations (for testing)."""
    _registry.clear()


def _resolve_chain(
    product: str, from_version: int, to_version: int
) -> list[tuple[int, int, MigrationCallable]]:
    """Build an ordered list of (from, to, callable) steps to reach *to_version*.

    Uses a simple greedy walk: at each step pick the registered migration
    whose ``from_version`` matches the current version.
    """
    chain: list[tuple[int, int, MigrationCallable]] = []
    current = from_version
    while current < to_version:
        key = (product, current, current + 1)
        if key not in _registry:
            raise MigrationError(
                f"No migration registered for {product!r} v{current} -> v{current + 1}"
            )
        chain.append((current, current + 1, _registry[key]))
        current += 1
    return chain


def _copy_root_attrs(src: h5py.File, dst: h5py.File) -> None:
    """Copy all root-level attributes from *src* to *dst*."""
    for key in src.attrs:
        dst.attrs[key] = src.attrs[key]


def migrate(
    source_path: str | Path,
    dest_path: str | Path,
    *,
    target_version: int,
) -> Path:
    """Migrate an fd5 file to *target_version*, producing a new file at *dest_path*.

    1. Read ``_schema_version`` and ``product`` from the source file.
    2. Resolve the chain of registered migration callables.
    3. Apply each step in sequence (intermediate files use tempdir).
    4. Write provenance ``sources/migrated_from`` linking to the original.
    5. Recompute ``content_hash``.

    Returns the resolved *dest_path*.
    """
    source_path = Path(source_path)
    dest_path = Path(dest_path)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    with h5py.File(source_path, "r") as src:
        current_version = int(src.attrs["_schema_version"])
        product = src.attrs["product"]
        if isinstance(product, bytes):
            product = product.decode()
        original_content_hash = src.attrs.get("content_hash", "")
        if isinstance(original_content_hash, bytes):
            original_content_hash = original_content_hash.decode()
        original_id = src.attrs.get("id", "")
        if isinstance(original_id, bytes):
            original_id = original_id.decode()

    if current_version >= target_version:
        raise MigrationError(
            f"File is already at version {current_version}, "
            f"cannot migrate to {target_version}"
        )

    chain = _resolve_chain(product, current_version, target_version)

    prev_path = source_path
    tmp_files: list[Path] = []

    try:
        for step_idx, (v_from, v_to, fn) in enumerate(chain):
            is_last = step_idx == len(chain) - 1
            if is_last:
                next_path = dest_path
            else:
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".h5", delete=False, dir=dest_path.parent
                )
                tmp.close()
                next_path = Path(tmp.name)
                tmp_files.append(next_path)

            with h5py.File(prev_path, "r") as src, h5py.File(next_path, "w") as dst:
                _copy_root_attrs(src, dst)
                fn(src, dst)
                dst.attrs["_schema_version"] = np.int64(v_to)

            prev_path = next_path

        with h5py.File(dest_path, "a") as dst:
            _write_migration_provenance(
                dst,
                source_path=source_path,
                product=product,
                original_id=original_id,
                original_content_hash=original_content_hash,
            )
            dst.attrs["content_hash"] = compute_content_hash(dst)

    finally:
        for tmp in tmp_files:
            if tmp.exists():
                tmp.unlink()

    return dest_path


def _write_migration_provenance(
    dst: h5py.File,
    *,
    source_path: Path,
    product: str,
    original_id: str,
    original_content_hash: str,
) -> None:
    """Record the migration source in ``sources/migrated_from``."""
    write_sources(
        dst,
        [
            {
                "name": "migrated_from",
                "id": original_id,
                "product": product,
                "file": str(source_path),
                "content_hash": original_content_hash,
                "role": "migration_source",
                "description": "Source file before schema migration",
            }
        ],
    )
