"""fd5.ingest.csv — CSV/TSV tabular data loader.

Reads CSV/TSV files and produces sealed fd5 files targeting tabular
scientific data: spectra, calibration curves, time series, device logs.
Uses stdlib ``csv`` and ``numpy`` — no pandas dependency required.
"""

from __future__ import annotations

import csv as csv_mod
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from fd5._types import Fd5Path
from fd5.create import create
from fd5.ingest._base import hash_source_files

__version__ = "0.1.0"

_COMMENT_META_RE = re.compile(r"^\s*(\w[\w\s]*\w|\w+)\s*:\s*(.+)\s*$")

_SPECTRUM_COUNTS_ALIASES = frozenset({"counts", "count", "intensity", "rate", "y"})
_SPECTRUM_ENERGY_ALIASES = frozenset(
    {"energy", "channel", "bin", "x", "wavelength", "frequency"}
)


class CsvLoader:
    """Loader that reads CSV/TSV files and produces sealed fd5 files."""

    @property
    def supported_product_types(self) -> list[str]:
        return ["spectrum", "calibration", "device_data"]

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
        delimiter: str = ",",
        header_row: int = 0,
        comment: str = "#",
        **kwargs: Any,
    ) -> Fd5Path:
        """Read a CSV/TSV file and produce a sealed fd5 file."""
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        ts = timestamp or datetime.now(tz=timezone.utc).isoformat()

        comment_meta = _extract_comment_metadata(source, comment)
        headers, rows = _read_csv(source, delimiter, header_row, comment)

        if len(rows) == 0:
            raise ValueError(f"No data rows found in {source}")

        columns = _parse_columns(headers, rows)

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
            headers=headers,
            column_map=column_map,
            comment_meta=comment_meta,
            file_records=file_records,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# CSV parsing helpers
# ---------------------------------------------------------------------------


def _extract_comment_metadata(path: Path, comment: str) -> dict[str, str]:
    """Parse ``# key: value`` lines from the top of the file."""
    meta: dict[str, str] = {}
    with path.open() as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped.startswith(comment):
                break
            content = stripped[len(comment) :].strip()
            m = _COMMENT_META_RE.match(content)
            if m:
                meta[m.group(1).strip()] = m.group(2).strip()
    return meta


def _read_csv(
    path: Path,
    delimiter: str,
    header_row: int,
    comment: str,
) -> tuple[list[str], list[list[str]]]:
    """Read CSV, skipping comment lines, returning headers and data rows."""
    with path.open(newline="") as fh:
        lines = fh.readlines()

    non_comment = [line for line in lines if not line.strip().startswith(comment)]

    if header_row >= len(non_comment):
        raise ValueError(
            f"header_row={header_row} but only {len(non_comment)} non-comment lines"
        )

    reader = csv_mod.reader(
        io.StringIO("".join(non_comment[header_row:])),
        delimiter=delimiter,
    )
    all_rows = list(reader)
    if not all_rows:
        return [], []

    headers = [h.strip() for h in all_rows[0]]
    data_rows = [row for row in all_rows[1:] if any(cell.strip() for cell in row)]
    return headers, data_rows


def _parse_columns(
    headers: list[str], rows: list[list[str]]
) -> dict[str, np.ndarray | list[str]]:
    """Parse columns, inferring numeric vs string type per column."""
    columns: dict[str, np.ndarray | list[str]] = {}
    for i, header in enumerate(headers):
        raw = [row[i].strip() if i < len(row) else "" for row in rows]
        try:
            arr = np.array([float(v) for v in raw], dtype=np.float64)
            columns[header] = arr
        except ValueError:
            columns[header] = raw
    return columns


# ---------------------------------------------------------------------------
# Shared writer helper
# ---------------------------------------------------------------------------


def _find_output_file(output_dir: Path) -> Fd5Path:
    """Find the sealed fd5 file in *output_dir* after create() exits."""
    files = sorted(output_dir.glob("*.h5"), key=lambda p: p.stat().st_mtime)
    return files[-1]


# ---------------------------------------------------------------------------
# Product-specific writers
# ---------------------------------------------------------------------------


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


def _write_spectrum(
    *,
    source: Path,
    output_dir: Path,
    product: str,
    name: str,
    description: str,
    timestamp: str,
    columns: dict[str, Any],
    headers: list[str],
    column_map: dict[str, str] | None,
    comment_meta: dict[str, str],
    file_records: list[dict[str, Any]],
    **kwargs: Any,
) -> Fd5Path:
    """Write spectrum product from CSV columns."""
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
        units = comment_meta.get("units", "arb")
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

        if comment_meta:
            builder.write_metadata(comment_meta)

        builder.write_provenance(
            original_files=file_records,
            ingest_tool="fd5.ingest.csv",
            ingest_version=__version__,
            ingest_timestamp=timestamp,
        )

    return _find_output_file(output_dir)


def _write_calibration(
    *,
    source: Path,
    output_dir: Path,
    product: str,
    name: str,
    description: str,
    timestamp: str,
    columns: dict[str, Any],
    headers: list[str],
    column_map: dict[str, str] | None,
    comment_meta: dict[str, str],
    file_records: list[dict[str, Any]],
    calibration_type: str = "energy_calibration",
    scanner_model: str = "unknown",
    scanner_serial: str = "unknown",
    valid_from: str = "",
    valid_until: str = "indefinite",
    **kwargs: Any,
) -> Fd5Path:
    """Write calibration product from CSV columns."""
    product_data: dict[str, Any] = {
        "calibration_type": calibration_type,
        "scanner_model": scanner_model,
        "scanner_serial": scanner_serial,
        "valid_from": valid_from,
        "valid_until": valid_until,
    }

    if calibration_type == "energy_calibration" and "input" in columns:
        product_data["channel_to_energy"] = np.asarray(
            columns["input"], dtype=np.float64
        )

    with create(
        output_dir,
        product=product,
        name=name,
        description=description,
        timestamp=timestamp,
    ) as builder:
        builder.write_product(product_data)

        if comment_meta:
            builder.write_metadata(comment_meta)

        builder.write_provenance(
            original_files=file_records,
            ingest_tool="fd5.ingest.csv",
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
    columns: dict[str, Any],
    headers: list[str],
    column_map: dict[str, str] | None,
    comment_meta: dict[str, str],
    file_records: list[dict[str, Any]],
    device_type: str = "environmental_sensor",
    device_model: str = "unknown",
    **kwargs: Any,
) -> Fd5Path:
    """Write device_data product from CSV/TSV columns."""
    time_col = _resolve_column(
        columns,
        column_map,
        "timestamp",
        frozenset({"timestamp", "time", "t", "elapsed"}),
    )
    signal_cols = [
        h
        for h in headers
        if h != (time_col or "") and isinstance(columns.get(h), np.ndarray)
    ]

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
            "units": comment_meta.get("units", "arb"),
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

        if comment_meta:
            builder.write_metadata(comment_meta)

        builder.write_provenance(
            original_files=file_records,
            ingest_tool="fd5.ingest.csv",
            ingest_version=__version__,
            ingest_timestamp=timestamp,
        )

    return _find_output_file(output_dir)


_PRODUCT_WRITERS = {
    "spectrum": _write_spectrum,
    "calibration": _write_calibration,
    "device_data": _write_device_data,
}
