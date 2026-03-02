"""fd5.ingest.raw — raw/numpy array loader.

Wraps raw numpy arrays or binary files into sealed fd5 files.
Serves as the reference Loader implementation and fallback when
no format-specific loader is needed.
"""

from __future__ import annotations

import importlib.metadata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from fd5._types import Fd5Path
from fd5.create import create
from fd5.ingest._base import hash_source_files
from fd5.registry import list_schemas

__all__ = ["RawLoader", "ingest_array", "ingest_binary"]

_INGEST_TOOL = "fd5.ingest.raw"


def _fd5_version() -> str:
    try:
        return importlib.metadata.version("fd5")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def ingest_array(
    data: dict[str, Any],
    output_dir: Path,
    *,
    product: str,
    name: str,
    description: str,
    timestamp: str | None = None,
    metadata: dict[str, Any] | None = None,
    study_metadata: dict[str, Any] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> Fd5Path:
    """Wrap a data dict into a sealed fd5 file.

    The data dict is passed directly to the product schema's ``write()`` method.

    Returns:
        Path to the sealed fd5 file.

    Raises:
        ValueError: If *product* is not a registered product type.
    """
    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc).isoformat()

    output_dir = Path(output_dir)

    with create(
        output_dir,
        product=product,
        name=name,
        description=description,
        timestamp=timestamp,
    ) as builder:
        builder.write_product(data)

        if metadata is not None:
            builder.write_metadata(metadata)

        if sources is not None:
            builder.write_sources(sources)

        if study_metadata is not None:
            builder.write_study(**study_metadata)

    sealed_files = sorted(output_dir.glob("*.h5"))
    return sealed_files[-1]


def ingest_binary(
    binary_path: Path,
    output_dir: Path,
    *,
    dtype: str,
    shape: tuple[int, ...],
    product: str,
    name: str,
    description: str,
    timestamp: str | None = None,
    **kwargs: Any,
) -> Fd5Path:
    """Read a raw binary file, reshape, and produce a sealed fd5 file.

    The binary data is read via ``numpy.fromfile`` and reshaped to *shape*.
    Provenance records the source file's SHA-256.

    Additional keyword arguments are merged into the data dict passed to
    the product schema's ``write()`` method.

    Returns:
        Path to the sealed fd5 file.

    Raises:
        FileNotFoundError: If *binary_path* does not exist.
        ValueError: If the file size does not match *dtype* × *shape*.
    """
    binary_path = Path(binary_path)
    if not binary_path.exists():
        raise FileNotFoundError(f"Binary file not found: {binary_path}")

    raw = np.fromfile(binary_path, dtype=dtype)
    expected_size = 1
    for s in shape:
        expected_size *= s
    if raw.size != expected_size:
        msg = f"cannot reshape array of size {raw.size} into shape {shape}"
        raise ValueError(msg)

    arr = raw.reshape(shape)

    prov_records = hash_source_files([binary_path])

    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc).isoformat()

    data: dict[str, Any] = {"volume": arr, "description": description}
    data.update(kwargs)

    output_dir = Path(output_dir)

    with create(
        output_dir,
        product=product,
        name=name,
        description=description,
        timestamp=timestamp,
    ) as builder:
        builder.write_product(data)
        builder.write_provenance(
            original_files=prov_records,
            ingest_tool=_INGEST_TOOL,
            ingest_version=_fd5_version(),
            ingest_timestamp=timestamp,
        )

    sealed_files = sorted(output_dir.glob("*.h5"))
    return sealed_files[-1]


class RawLoader:
    """Loader implementation for raw numpy arrays and binary files.

    Satisfies the :class:`~fd5.ingest._base.Loader` protocol.
    """

    @property
    def supported_product_types(self) -> list[str]:
        return list_schemas()

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
        """Read a binary source file and produce a sealed fd5 file.

        Requires ``dtype`` and ``shape`` in *kwargs*.
        """
        return ingest_binary(
            Path(source),
            output_dir,
            product=product,
            name=name,
            description=description,
            timestamp=timestamp,
            **kwargs,
        )
