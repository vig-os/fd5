"""fd5.create — builder/context-manager API for creating sealed fd5 files.

Primary public API of fd5. Opens an HDF5 file, writes root attrs, delegates
to product schemas, computes hashes, and seals the file on context exit.

See white-paper.md § Immutability and write-once semantics.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from fd5.h5io import dict_to_h5
from fd5.hash import compute_content_hash, compute_id
from fd5.naming import generate_filename
from fd5.provenance import write_ingest, write_original_files, write_sources
from fd5.registry import get_schema
from fd5.schema import embed_schema


class Fd5ValidationError(Exception):
    """Raised when required attributes are missing or empty before sealing."""


class Fd5Builder:
    """Context-managed builder that orchestrates fd5 file creation.

    Do not instantiate directly — use :func:`create`.
    """

    def __init__(
        self,
        file: h5py.File,
        tmp_path: Path,
        out_dir: Path,
        product_type: str,
        name: str,
        description: str,
        timestamp: str,
    ) -> None:
        self._file = file
        self._tmp_path = tmp_path
        self._out_dir = out_dir
        self._product_type = product_type
        self._name = name
        self._description = description
        self._timestamp = timestamp
        self._schema = get_schema(product_type)

    @property
    def file(self) -> h5py.File:
        return self._file

    # -- writer methods ----------------------------------------------------

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        """Write ``metadata/`` group from *metadata* dict."""
        grp = self._file.create_group("metadata")
        dict_to_h5(grp, metadata)

    def write_sources(self, sources: list[dict[str, Any]]) -> None:
        """Write ``sources/`` group. Delegates to :func:`fd5.provenance.write_sources`."""
        write_sources(self._file, sources)

    def write_provenance(
        self,
        *,
        original_files: list[dict[str, Any]],
        ingest_tool: str,
        ingest_version: str,
        ingest_timestamp: str,
    ) -> None:
        """Write ``provenance/`` group with original_files and ingest sub-groups."""
        write_original_files(self._file, original_files)
        write_ingest(
            self._file,
            tool=ingest_tool,
            version=ingest_version,
            timestamp=ingest_timestamp,
        )

    def write_study(
        self,
        *,
        study_type: str,
        license: str,
        description: str,
        creators: list[dict[str, Any]] | None = None,
    ) -> None:
        """Write ``study/`` group with type, license, description, and optional creators."""
        grp = self._file.create_group("study")
        grp.attrs["type"] = study_type
        grp.attrs["license"] = license
        grp.attrs["description"] = description

        if creators:
            creators_grp = grp.create_group("creators")
            for idx, creator in enumerate(creators):
                sub = creators_grp.create_group(f"creator_{idx}")
                dict_to_h5(sub, creator)

    def write_extra(self, data: dict[str, Any]) -> None:
        """Write ``extra/`` group for unvalidated data."""
        grp = self._file.create_group("extra")
        grp.attrs["description"] = (
            "Unvalidated, vendor-specific, or experimental metadata"
        )
        dict_to_h5(grp, data)

    def write_product(self, data: Any) -> None:
        """Delegate product-specific writes to the registered ProductSchema."""
        self._schema.write(self._file, data)

    # -- sealing -----------------------------------------------------------

    def _validate(self) -> None:
        """Raise :class:`Fd5ValidationError` if required attrs are missing/empty."""
        for attr in ("name", "description", "timestamp"):
            val = self._file.attrs.get(attr, "")
            if isinstance(val, bytes):
                val = val.decode("utf-8")
            if not val:
                raise Fd5ValidationError(
                    f"Required attribute {attr!r} is missing or empty"
                )

    def _seal(self) -> Path:
        """Embed schema, compute hashes, write id, rename to final path."""
        self._validate()

        schema_dict = self._schema.json_schema()
        embed_schema(self._file, schema_dict)

        id_keys = self._schema.id_inputs()
        id_inputs = {}
        for key in id_keys:
            val = self._file.attrs.get(key, "")
            if isinstance(val, bytes):
                val = val.decode("utf-8")
            id_inputs[key] = str(val)

        id_desc = " + ".join(id_keys)
        file_id = compute_id(id_inputs, id_desc)
        self._file.attrs["id"] = file_id
        self._file.attrs["id_inputs"] = id_desc

        content_hash = compute_content_hash(self._file)
        self._file.attrs["content_hash"] = content_hash

        self._file.close()

        ts = _parse_timestamp(self._timestamp)
        product_slug = self._product_type.replace("/", "-")
        filename = generate_filename(
            product=product_slug,
            id_hash=file_id,
            timestamp=ts,
            descriptors=[],
        )
        final_path = self._out_dir / filename
        os.replace(self._tmp_path, final_path)
        return final_path


@contextmanager
def create(
    out_dir: str | Path,
    *,
    product: str,
    name: str,
    description: str,
    timestamp: str,
    schema_version: int = 1,
):
    """Context manager that creates a sealed fd5 file.

    On successful exit the file is sealed (schema embedded, hashes computed,
    file atomically renamed). On exception the incomplete temp file is deleted.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    get_schema(product)  # fail fast on unknown product type

    tmp_path = out_dir / f".fd5_{product.replace('/', '_')}.h5.tmp"
    f = h5py.File(tmp_path, "w")

    try:
        f.attrs["product"] = product
        f.attrs["name"] = name
        f.attrs["description"] = description
        f.attrs["timestamp"] = timestamp
        f.attrs["_schema_version"] = np.int64(schema_version)

        builder = Fd5Builder(
            file=f,
            tmp_path=tmp_path,
            out_dir=out_dir,
            product_type=product,
            name=name,
            description=description,
            timestamp=timestamp,
        )
        yield builder
        builder._seal()
    except BaseException:
        if not f.id or not f.id.valid:
            pass
        else:
            f.close()
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _parse_timestamp(ts: str) -> datetime | None:
    """Best-effort parse of an ISO 8601 timestamp string."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return datetime.now(tz=timezone.utc)
