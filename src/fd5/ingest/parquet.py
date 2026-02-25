"""fd5.ingest.parquet — Parquet columnar data loader.

Reads Apache Parquet files via pyarrow and produces sealed fd5 files.
Parquet's columnar layout and embedded schema map naturally to fd5's
typed datasets and attrs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from fd5._types import Fd5Path
from fd5.create import create
from fd5.ingest._base import hash_source_files

try:
    import pyarrow.parquet as pq
except ImportError as _exc:
    raise ImportError(
        "pyarrow is required for Parquet ingest. "
        "Install it with:  pip install 'fd5[parquet]'"
    ) from _exc

__version__ = "0.1.0"

_log = logging.getLogger(__name__)

_SPECTRUM_COUNTS_ALIASES = frozenset({"counts", "count", "intensity", "rate", "y"})
_SPECTRUM_ENERGY_ALIASES = frozenset(
    {"energy", "channel", "bin", "x", "wavelength", "frequency"}
)


class ParquetLoader:
    """Loader that reads Parquet files and produces sealed fd5 files."""

    @property
    def supported_product_types(self) -> list[str]:
        return ["spectrum", "listmode", "device_data"]

    def ingest(
        self,
        source: Path | str,
        output_dir: Path,
        *,
        product: str,
        name: str,
        description: str,
        timestamp: str | None = None,
        column_map: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Fd5Path:
        """Read a Parquet file and produce a sealed fd5 file."""
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        ts = timestamp or datetime.now(tz=timezone.utc).isoformat()

        table = pq.read_table(source)
        if table.num_rows == 0:
            raise ValueError(f"No data rows found in {source}")

        pq_metadata = _extract_parquet_metadata(source)
        columns = _table_to_columns(table)
        file_records = hash_source_files([source])

        writer = _PRODUCT_WRITERS.get(product, _write_spectrum)
        return writer(
            source=source,
            output_dir=output_dir,
            product=product,
            name=name,
            description=description,
            timestamp=ts,
            columns=columns,
            column_names=table.column_names,
            column_map=column_map,
            pq_metadata=pq_metadata,
            file_records=file_records,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Parquet reading helpers
# ---------------------------------------------------------------------------


def _extract_parquet_metadata(path: Path) -> dict[str, str]:
    """Extract key-value metadata from the Parquet file footer."""
    schema = pq.read_schema(path)
    raw = schema.metadata or {}
    meta: dict[str, str] = {}
    for k, v in raw.items():
        key = k.decode() if isinstance(k, bytes) else k
        val = v.decode() if isinstance(v, bytes) else v
        if not key.startswith("pandas") and not key.startswith("ARROW"):
            meta[key] = val
    return meta


def _table_to_columns(table: Any) -> dict[str, np.ndarray]:
    """Convert a PyArrow table to a dict of numpy arrays."""
    columns: dict[str, np.ndarray] = {}
    for col_name in table.column_names:
        columns[col_name] = table.column(col_name).to_numpy()
    return columns


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _find_output_file(output_dir: Path) -> Fd5Path:
    """Find the sealed fd5 file in *output_dir* after create() exits."""
    files = sorted(output_dir.glob("*.h5"), key=lambda p: p.stat().st_mtime)
    return files[-1]


def _resolve_column(
    columns: dict[str, Any],
    column_map: dict[str, str] | None,
    target_key: str,
    aliases: frozenset[str],
) -> str | None:
    """Find the source column name for *target_key* using mapping or aliases."""
    if column_map and target_key in column_map:
        mapped = column_map[target_key]
        if mapped in columns:
            return mapped
    for alias in aliases:
        if alias in columns:
            return alias
    return None


# ---------------------------------------------------------------------------
# Product-specific writers
# ---------------------------------------------------------------------------


def _write_spectrum(
    *,
    source: Path,
    output_dir: Path,
    product: str,
    name: str,
    description: str,
    timestamp: str,
    columns: dict[str, np.ndarray],
    column_names: list[str],
    column_map: dict[str, str] | None,
    pq_metadata: dict[str, str],
    file_records: list[dict[str, Any]],
    **kwargs: Any,
) -> Fd5Path:
    """Write spectrum product from Parquet columns."""
    counts_col = _resolve_column(
        columns, column_map, "counts", _SPECTRUM_COUNTS_ALIASES
    )
    energy_col = _resolve_column(
        columns, column_map, "energy", _SPECTRUM_ENERGY_ALIASES
    )

    if counts_col is None:
        raise ValueError(
            f"Cannot find counts column. Available: {list(columns.keys())}"
        )

    counts = np.asarray(columns[counts_col], dtype=np.float32)

    axes = []
    if energy_col is not None:
        energy_vals = np.asarray(columns[energy_col], dtype=np.float64)
        units = pq_metadata.get("units", "arb")
        half_step = 0.0
        if len(energy_vals) > 1:
            half_step = (energy_vals[1] - energy_vals[0]) / 2.0
        bin_edges = np.append(energy_vals - half_step, energy_vals[-1] + half_step)
        axes.append(
            {
                "label": energy_col,
                "units": units,
                "unitSI": 1.0,
                "bin_edges": bin_edges,
                "description": f"{energy_col} axis",
            }
        )

    product_data: dict[str, Any] = {"counts": counts}
    if axes:
        product_data["axes"] = axes

    with create(
        output_dir,
        product=product,
        name=name,
        description=description,
        timestamp=timestamp,
    ) as builder:
        builder.write_product(product_data)

        if pq_metadata:
            builder.write_metadata(pq_metadata)

        builder.write_provenance(
            original_files=file_records,
            ingest_tool="fd5.ingest.parquet",
            ingest_version=__version__,
            ingest_timestamp=timestamp,
        )

    return _find_output_file(output_dir)


def _write_listmode(
    *,
    source: Path,
    output_dir: Path,
    product: str,
    name: str,
    description: str,
    timestamp: str,
    columns: dict[str, np.ndarray],
    column_names: list[str],
    column_map: dict[str, str] | None,
    pq_metadata: dict[str, str],
    file_records: list[dict[str, Any]],
    mode: str = "3d",
    table_pos: float = 0.0,
    z_min: float = 0.0,
    z_max: float = 0.0,
    **kwargs: Any,
) -> Fd5Path:
    """Write listmode product — columns placed in raw_data group."""
    time_col = _resolve_column(
        columns,
        column_map,
        "time",
        frozenset({"time", "timestamp", "t", "elapsed"}),
    )
    time_arr = (
        np.asarray(columns[time_col], dtype=np.float64)
        if time_col
        else np.arange(len(next(iter(columns.values()))), dtype=np.float64)
    )
    duration = float(time_arr[-1] - time_arr[0]) if len(time_arr) > 1 else 0.0

    raw_datasets: dict[str, np.ndarray] = {}
    for col_name in column_names:
        raw_datasets[col_name] = np.asarray(columns[col_name])

    product_data: dict[str, Any] = {
        "mode": mode,
        "table_pos": table_pos,
        "duration": duration,
        "z_min": z_min,
        "z_max": z_max,
        "raw_data": raw_datasets,
    }

    with create(
        output_dir,
        product=product,
        name=name,
        description=description,
        timestamp=timestamp,
    ) as builder:
        builder.write_product(product_data)

        if pq_metadata:
            builder.write_metadata(pq_metadata)

        builder.write_provenance(
            original_files=file_records,
            ingest_tool="fd5.ingest.parquet",
            ingest_version=__version__,
            ingest_timestamp=timestamp,
        )

    return _find_output_file(output_dir)


def _write_device_data(
    *,
    source: Path,
    output_dir: Path,
    product: str,
    name: str,
    description: str,
    timestamp: str,
    columns: dict[str, np.ndarray],
    column_names: list[str],
    column_map: dict[str, str] | None,
    pq_metadata: dict[str, str],
    file_records: list[dict[str, Any]],
    device_type: str = "environmental_sensor",
    device_model: str = "unknown",
    **kwargs: Any,
) -> Fd5Path:
    """Write device_data product from Parquet columns."""
    time_col = _resolve_column(
        columns,
        column_map,
        "timestamp",
        frozenset({"timestamp", "time", "t", "elapsed"}),
    )
    signal_cols = [h for h in column_names if h != (time_col or "") and h in columns]

    time_arr = (
        np.asarray(columns[time_col], dtype=np.float64)
        if time_col
        else np.arange(len(next(iter(columns.values()))), dtype=np.float64)
    )

    duration = float(time_arr[-1] - time_arr[0]) if len(time_arr) > 1 else 0.0

    channels: dict[str, dict[str, Any]] = {}
    for col_name in signal_cols:
        signal = np.asarray(columns[col_name], dtype=np.float64)
        sampling_rate = len(signal) / max(duration, 1.0)
        channels[col_name] = {
            "signal": signal,
            "time": time_arr,
            "sampling_rate": sampling_rate,
            "units": pq_metadata.get("units", "arb"),
            "unitSI": 1.0,
            "description": f"{col_name} channel",
        }

    product_data: dict[str, Any] = {
        "device_type": device_type,
        "device_model": device_model,
        "recording_start": timestamp,
        "recording_duration": duration,
        "channels": channels,
    }

    with create(
        output_dir,
        product=product,
        name=name,
        description=description,
        timestamp=timestamp,
    ) as builder:
        builder.write_product(product_data)

        builder.write_provenance(
            original_files=file_records,
            ingest_tool="fd5.ingest.parquet",
            ingest_version=__version__,
            ingest_timestamp=timestamp,
        )

    return _find_output_file(output_dir)


_PRODUCT_WRITERS = {
    "spectrum": _write_spectrum,
    "listmode": _write_listmode,
    "device_data": _write_device_data,
}
