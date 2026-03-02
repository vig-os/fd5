"""Generate canonical fd5 fixture files for cross-language conformance testing.

Run via pytest (session-scoped autouse fixture) or standalone:
    uv run python -m tests.conformance.generate_fixtures
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np

from fd5.create import create
from fd5.hash import compute_content_hash
from fd5.registry import register_schema
from fd5.schema import embed_schema

TIMESTAMP = "2026-01-01T00:00:00Z"


class _ConformanceSchema:
    """Minimal product schema for conformance testing."""

    product_type: str = "test/conformance"
    schema_version: str = "1.0.0"

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "test/conformance"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "timestamp": {"type": "string"},
            },
            "required": ["_schema_version", "product", "name"],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {"product": "test/conformance"}

    def write(self, target: Any, data: Any) -> None:
        target.create_dataset("volume", data=data)

    def id_inputs(self) -> list[str]:
        return ["product", "name", "timestamp"]


def _register_schemas() -> None:
    import fd5.registry as reg

    reg._ensure_loaded()
    register_schema("test/conformance", _ConformanceSchema())


def _unregister_schemas() -> None:
    import fd5.registry as reg

    reg._registry.pop("test/conformance", None)


def _create_minimal(fixtures_dir: Path) -> Path:
    """Smallest valid fd5 file."""
    data = np.zeros((4, 4), dtype=np.float32)
    with create(
        fixtures_dir,
        product="test/conformance",
        name="minimal-conformance",
        description="Minimal conformance fixture",
        timestamp=TIMESTAMP,
    ) as builder:
        builder.write_product(data)

    return _find_and_rename(fixtures_dir, "minimal.fd5")


def _create_sealed(fixtures_dir: Path) -> Path:
    """File with verified content hash for hash verification tests."""
    data = np.arange(64, dtype=np.float32).reshape(8, 8)
    with create(
        fixtures_dir,
        product="test/conformance",
        name="sealed-conformance",
        description="Sealed conformance fixture",
        timestamp=TIMESTAMP,
    ) as builder:
        builder.write_product(data)

    return _find_and_rename(fixtures_dir, "sealed.fd5")


def _create_with_provenance(fixtures_dir: Path) -> Path:
    """File with source links and provenance data."""
    data = np.zeros((4, 4), dtype=np.float32)
    with create(
        fixtures_dir,
        product="test/conformance",
        name="provenance-conformance",
        description="Provenance conformance fixture",
        timestamp=TIMESTAMP,
    ) as builder:
        builder.write_product(data)
        builder.write_sources(
            [
                {
                    "name": "upstream",
                    "id": "sha256:aaa111",
                    "product": "raw",
                    "file": "upstream.h5",
                    "content_hash": "sha256:bbb222",
                    "role": "input_data",
                    "description": "Upstream raw data",
                }
            ]
        )
        builder.write_provenance(
            original_files=[
                {
                    "path": "/data/raw/scan.dcm",
                    "sha256": "sha256:ccc333",
                    "size_bytes": 4096,
                }
            ],
            ingest_tool="conformance_generator",
            ingest_version="1.0.0",
            ingest_timestamp=TIMESTAMP,
        )

    return _find_and_rename(fixtures_dir, "with-provenance.fd5")


def _create_multiscale(fixtures_dir: Path) -> Path:
    """File with pyramid/multiscale datasets using recon schema."""
    rng = np.random.default_rng(42)
    volume = rng.standard_normal((8, 8, 8)).astype(np.float32)

    with create(
        fixtures_dir,
        product="recon",
        name="multiscale-conformance",
        description="Multiscale conformance fixture",
        timestamp=TIMESTAMP,
    ) as builder:
        builder.write_product(
            {
                "volume": volume,
                "affine": np.eye(4, dtype=np.float64),
                "dimension_order": "ZYX",
                "reference_frame": "LPS",
                "description": "Test volume for multiscale conformance",
                "pyramid": {
                    "scale_factors": [2, 4],
                    "method": "stride",
                },
            }
        )
        builder.file.attrs["scanner"] = "test-scanner"
        builder.file.attrs["vendor_series_id"] = "test-series-001"

    return _find_and_rename(fixtures_dir, "multiscale.fd5")


def _create_tabular(fixtures_dir: Path) -> Path:
    """Compound dataset (event table) with typed columns."""
    volume_data = np.zeros((4, 4), dtype=np.float32)

    dt = np.dtype(
        [
            ("time", np.float64),
            ("energy", np.float32),
            ("detector_id", np.int32),
        ]
    )
    events = np.array(
        [
            (0.0, 511.0, 1),
            (0.1, 510.5, 2),
            (0.2, 511.2, 1),
            (0.3, 509.8, 3),
            (0.4, 511.0, 2),
        ],
        dtype=dt,
    )

    with create(
        fixtures_dir,
        product="test/conformance",
        name="tabular-conformance",
        description="Tabular conformance fixture",
        timestamp=TIMESTAMP,
    ) as builder:
        builder.write_product(volume_data)
        builder.file.create_dataset("events", data=events)

    return _find_and_rename(fixtures_dir, "tabular.fd5")


def _create_complex_metadata(fixtures_dir: Path) -> Path:
    """Deeply nested metadata groups."""
    volume_data = np.zeros((4, 4), dtype=np.float32)

    with create(
        fixtures_dir,
        product="test/conformance",
        name="complex-metadata-conformance",
        description="Complex metadata conformance fixture",
        timestamp=TIMESTAMP,
    ) as builder:
        builder.write_product(volume_data)
        builder.write_metadata(
            {
                "version": 2,
                "acquisition": {
                    "modality": "PET",
                    "duration_sec": 300.0,
                    "isotope": "F-18",
                },
                "reconstruction": {
                    "algorithm": "osem",
                    "parameters": {
                        "iterations": 4,
                        "subsets": 21,
                    },
                },
            }
        )

    return _find_and_rename(fixtures_dir, "complex-metadata.fd5")


def _create_invalid_missing_id(invalid_dir: Path) -> None:
    """File missing required root 'id' attribute."""
    path = invalid_dir / "missing-id.fd5"
    with h5py.File(path, "w") as f:
        f.attrs["product"] = "test/conformance"
        f.attrs["name"] = "missing-id"
        f.attrs["description"] = "Missing id attribute"
        f.attrs["timestamp"] = TIMESTAMP
        f.attrs["_schema_version"] = np.int64(1)
        f.create_dataset("volume", data=np.zeros((4, 4), dtype=np.float32))
        schema_dict = _ConformanceSchema().json_schema()
        embed_schema(f, schema_dict)
        f.attrs["content_hash"] = compute_content_hash(f)


def _create_invalid_bad_hash(invalid_dir: Path) -> None:
    """File whose content_hash doesn't match actual content."""
    path = invalid_dir / "bad-hash.fd5"
    with h5py.File(path, "w") as f:
        f.attrs["product"] = "test/conformance"
        f.attrs["name"] = "bad-hash"
        f.attrs["description"] = "Bad hash fixture"
        f.attrs["timestamp"] = TIMESTAMP
        f.attrs["_schema_version"] = np.int64(1)
        f.attrs["id"] = "sha256:fake_id_not_real"
        f.create_dataset("volume", data=np.zeros((4, 4), dtype=np.float32))
        schema_dict = _ConformanceSchema().json_schema()
        embed_schema(f, schema_dict)
        f.attrs["content_hash"] = (
            "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        )


def _create_invalid_no_schema(invalid_dir: Path) -> None:
    """File missing the _schema attribute."""
    path = invalid_dir / "no-schema.fd5"
    with h5py.File(path, "w") as f:
        f.attrs["product"] = "test/conformance"
        f.attrs["name"] = "no-schema"
        f.attrs["description"] = "No schema fixture"
        f.attrs["timestamp"] = TIMESTAMP
        f.attrs["_schema_version"] = np.int64(1)
        f.attrs["id"] = "sha256:fake_id_not_real"
        f.create_dataset("volume", data=np.zeros((4, 4), dtype=np.float32))
        f.attrs["content_hash"] = compute_content_hash(f)


def _find_and_rename(directory: Path, target_name: str) -> Path:
    """Find the single .h5 file created by fd5.create() and rename it."""
    h5_files = list(directory.glob("*.h5"))
    unnamed = [f for f in h5_files if not f.stem.endswith(".fd5")]
    if not unnamed:
        unnamed = h5_files
    newest = max(unnamed, key=lambda f: f.stat().st_mtime)
    target = directory / target_name
    if target.exists():
        target.unlink()
    newest.rename(target)
    return target


def generate_all(fixtures_dir: Path, invalid_dir: Path) -> None:
    """Generate all conformance fixture files."""
    _register_schemas()

    fixtures_dir.mkdir(parents=True, exist_ok=True)
    invalid_dir.mkdir(parents=True, exist_ok=True)

    for existing in fixtures_dir.glob("*.fd5"):
        existing.unlink()
    for existing in fixtures_dir.glob("*.h5"):
        existing.unlink()
    for existing in invalid_dir.glob("*.fd5"):
        existing.unlink()

    try:
        _create_minimal(fixtures_dir)
        _create_sealed(fixtures_dir)
        _create_with_provenance(fixtures_dir)
        _create_multiscale(fixtures_dir)
        _create_tabular(fixtures_dir)
        _create_complex_metadata(fixtures_dir)

        _create_invalid_missing_id(invalid_dir)
        _create_invalid_bad_hash(invalid_dir)
        _create_invalid_no_schema(invalid_dir)
    finally:
        _unregister_schemas()


if __name__ == "__main__":
    conformance_dir = Path(__file__).parent
    generate_all(conformance_dir / "fixtures", conformance_dir / "invalid")
    print("All conformance fixtures generated.")
