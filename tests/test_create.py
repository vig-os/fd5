"""Tests for fd5.create — Fd5Builder context-manager API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

from fd5.hash import verify
from fd5.registry import register_schema


# ---------------------------------------------------------------------------
# Stub schema
# ---------------------------------------------------------------------------


class _StubSchema:
    """Minimal ProductSchema for builder tests."""

    product_type: str = "test/product"
    schema_version: str = "1.0.0"

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "test/product"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "timestamp": {"type": "string"},
            },
            "required": ["_schema_version", "product", "name"],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {"product": "test/product"}

    def write(self, target: Any, data: Any) -> None:
        target.create_dataset("volume", data=data)

    def id_inputs(self) -> list[str]:
        return ["product", "name", "timestamp"]


@pytest.fixture(autouse=True)
def _register_stub():
    import fd5.registry as reg

    register_schema("test/product", _StubSchema())
    reg._ep_loaded = True


@pytest.fixture()
def out_dir(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


from fd5.create import Fd5Builder, Fd5ValidationError, create  # noqa: E402


# ---------------------------------------------------------------------------
# create() returns a context manager
# ---------------------------------------------------------------------------


class TestCreateReturnsContextManager:
    def test_returns_fd5builder(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="A test file",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            assert isinstance(builder, Fd5Builder)

    def test_builder_exposes_h5_file(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="A test file",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            assert isinstance(builder.file, h5py.File)


# ---------------------------------------------------------------------------
# Root attrs on entry
# ---------------------------------------------------------------------------


class TestRootAttrsOnEntry:
    def test_product_attr_written(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            assert builder.file.attrs["product"] == "test/product"

    def test_name_attr_written(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="my-name",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            assert builder.file.attrs["name"] == "my-name"

    def test_description_attr_written(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="A description",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            assert builder.file.attrs["description"] == "A description"

    def test_timestamp_attr_written(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            assert builder.file.attrs["timestamp"] == "2026-02-25T12:00:00Z"

    def test_schema_version_attr_written(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            assert builder.file.attrs["_schema_version"] == 1


# ---------------------------------------------------------------------------
# Builder methods
# ---------------------------------------------------------------------------


class TestWriteMetadata:
    def test_write_metadata_creates_group(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            builder.write_metadata({"algorithm": "osem", "iterations": 4})
            assert "metadata" in builder.file
            assert builder.file["metadata"].attrs["algorithm"] == "osem"


class TestWriteSources:
    def test_write_sources_creates_group(self, out_dir: Path):
        sources = [
            {
                "name": "emission",
                "id": "sha256:abc123",
                "product": "listmode",
                "file": "input.h5",
                "content_hash": "sha256:def456",
                "role": "emission_data",
                "description": "test source",
            }
        ]
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            builder.write_sources(sources)
            assert "sources" in builder.file


class TestWriteProvenance:
    def test_write_provenance_creates_group(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            builder.write_provenance(
                original_files=[
                    {"path": "/raw.dcm", "sha256": "sha256:abc", "size_bytes": 100}
                ],
                ingest_tool="my_tool",
                ingest_version="1.0",
                ingest_timestamp="2026-02-25T12:00:00Z",
            )
            assert "provenance" in builder.file
            assert "original_files" in builder.file["provenance"]
            assert "ingest" in builder.file["provenance"]


class TestWriteStudy:
    def test_write_study_creates_group(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            builder.write_study(
                study_type="research",
                license="CC-BY-4.0",
                description="A research study",
            )
            assert "study" in builder.file
            assert builder.file["study"].attrs["type"] == "research"
            assert builder.file["study"].attrs["license"] == "CC-BY-4.0"
            assert builder.file["study"].attrs["description"] == "A research study"

    def test_write_study_with_creators(self, out_dir: Path):
        creators = [
            {
                "name": "Jane Doe",
                "affiliation": "MIT",
                "orcid": "0000-0001-2345-6789",
                "role": "PI",
                "description": "Principal Investigator",
            }
        ]
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            builder.write_study(
                study_type="clinical",
                license="CC0-1.0",
                description="Clinical trial",
                creators=creators,
            )
            assert "creators" in builder.file["study"]
            assert "creator_0" in builder.file["study/creators"]
            assert builder.file["study/creators/creator_0"].attrs["name"] == "Jane Doe"


# ---------------------------------------------------------------------------
# Extra group
# ---------------------------------------------------------------------------


class TestExtraGroup:
    def test_write_extra_creates_group(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            builder.write_extra({"vendor_key": "vendor_value"})
            assert "extra" in builder.file
            assert builder.file["extra"].attrs["vendor_key"] == "vendor_value"


# ---------------------------------------------------------------------------
# Product schema delegation
# ---------------------------------------------------------------------------


class TestProductSchemaDelegation:
    def test_write_product_delegates_to_schema(self, out_dir: Path):
        data = np.zeros((4, 4), dtype=np.float32)
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            builder.write_product(data)
            assert "volume" in builder.file


# ---------------------------------------------------------------------------
# Sealing on __exit__ (success path)
# ---------------------------------------------------------------------------


class TestSealOnExit:
    def test_schema_embedded(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ):
            pass

        final = _find_h5(out_dir)
        with h5py.File(final, "r") as f:
            raw = f.attrs["_schema"]
            schema = json.loads(raw)
            assert schema["type"] == "object"

    def test_content_hash_written(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ):
            pass

        final = _find_h5(out_dir)
        with h5py.File(final, "r") as f:
            assert "content_hash" in f.attrs
            assert f.attrs["content_hash"].startswith("sha256:")

    def test_id_computed(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ):
            pass

        final = _find_h5(out_dir)
        with h5py.File(final, "r") as f:
            assert "id" in f.attrs
            assert f.attrs["id"].startswith("sha256:")

    def test_id_inputs_written(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ):
            pass

        final = _find_h5(out_dir)
        with h5py.File(final, "r") as f:
            assert "id_inputs" in f.attrs

    def test_content_hash_verifies(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ):
            pass

        final = _find_h5(out_dir)
        assert verify(final) is True

    def test_file_renamed_to_final_path(self, out_dir: Path):
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ):
            pass

        finals = list(out_dir.glob("*.h5"))
        assert len(finals) == 1
        assert "test_product" in finals[0].name or "test-product" in finals[0].name


# ---------------------------------------------------------------------------
# Exception path — cleanup
# ---------------------------------------------------------------------------


class TestExceptionCleanup:
    def test_incomplete_file_deleted_on_exception(self, out_dir: Path):
        with pytest.raises(RuntimeError, match="deliberate"):
            with create(
                out_dir,
                product="test/product",
                name="sample",
                description="desc",
                timestamp="2026-02-25T12:00:00Z",
            ):
                raise RuntimeError("deliberate failure")

        h5_files = list(out_dir.glob("*.h5"))
        tmp_files = list(out_dir.glob("*.h5.tmp"))
        assert len(h5_files) == 0
        assert len(tmp_files) == 0


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class TestValidationErrors:
    def test_unknown_product_raises_valueerror(self, out_dir: Path):
        with pytest.raises(ValueError, match="no-such-product"):
            with create(
                out_dir,
                product="no-such-product",
                name="sample",
                description="desc",
                timestamp="2026-02-25T12:00:00Z",
            ):
                pass

    def test_missing_name_raises_fd5_validation_error(self, out_dir: Path):
        with pytest.raises(Fd5ValidationError, match="name"):
            with create(
                out_dir,
                product="test/product",
                name="",
                description="desc",
                timestamp="2026-02-25T12:00:00Z",
            ):
                pass

    def test_missing_description_raises_fd5_validation_error(self, out_dir: Path):
        with pytest.raises(Fd5ValidationError, match="description"):
            with create(
                out_dir,
                product="test/product",
                name="sample",
                description="",
                timestamp="2026-02-25T12:00:00Z",
            ):
                pass

    def test_missing_timestamp_raises_fd5_validation_error(self, out_dir: Path):
        with pytest.raises(Fd5ValidationError, match="timestamp"):
            with create(
                out_dir,
                product="test/product",
                name="sample",
                description="desc",
                timestamp="",
            ):
                pass


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_creating_two_files_with_same_id_inputs_produces_same_id(
        self, out_dir: Path
    ):
        ids = []
        for i in range(2):
            subdir = out_dir / str(i)
            subdir.mkdir()
            with create(
                subdir,
                product="test/product",
                name="sample",
                description="desc",
                timestamp="2026-02-25T12:00:00Z",
            ):
                pass
            final = _find_h5(subdir)
            with h5py.File(final, "r") as f:
                ids.append(f.attrs["id"])
        assert ids[0] == ids[1]


# ---------------------------------------------------------------------------
# _validate with bytes attrs (create.py:128)
# ---------------------------------------------------------------------------


class TestValidateBytesAttrs:
    def test_validate_decodes_bytes_attr(self, out_dir: Path):
        """Covers create.py:128 — _validate decoding bytes attr values."""
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            builder.file.attrs["name"] = np.bytes_(b"sample")
            builder.file.attrs["description"] = np.bytes_(b"desc")
            builder.file.attrs["timestamp"] = np.bytes_(b"2026-02-25T12:00:00Z")

        final = _find_h5(out_dir)
        assert final.exists()


# ---------------------------------------------------------------------------
# _seal with bytes id_input attrs (create.py:146)
# ---------------------------------------------------------------------------


class TestSealBytesIdInputs:
    def test_seal_decodes_bytes_id_input(self, out_dir: Path):
        """Covers create.py:146 — _seal decoding bytes id_input values."""
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="2026-02-25T12:00:00Z",
        ) as builder:
            builder.file.attrs["product"] = np.bytes_(b"test/product")

        final = _find_h5(out_dir)
        with h5py.File(final, "r") as f:
            assert f.attrs["id"].startswith("sha256:")


# ---------------------------------------------------------------------------
# _parse_timestamp edge cases (create.py:226,229-230)
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_empty_timestamp_returns_none(self):
        """Covers create.py:226 — empty ts returns None."""
        from fd5.create import _parse_timestamp

        assert _parse_timestamp("") is None

    def test_invalid_timestamp_falls_back_to_now(self, out_dir: Path):
        """Covers create.py:229-230 — invalid ISO format falls back to datetime.now."""
        with create(
            out_dir,
            product="test/product",
            name="sample",
            description="desc",
            timestamp="not-a-valid-iso-timestamp",
        ):
            pass

        final = _find_h5(out_dir)
        assert final.exists()


# ---------------------------------------------------------------------------
# Exception path when file handle already invalid (create.py:214-215)
# ---------------------------------------------------------------------------


class TestExceptionFileHandleInvalid:
    def test_exception_after_file_closed(self, out_dir: Path):
        """Covers create.py:214-215 — f.id invalid when exception raised after close."""
        with pytest.raises(RuntimeError, match="after close"):
            with create(
                out_dir,
                product="test/product",
                name="sample",
                description="desc",
                timestamp="2026-02-25T12:00:00Z",
            ) as builder:
                builder.file.close()
                raise RuntimeError("after close")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_h5(directory: Path) -> Path:
    """Return the single .h5 file in *directory*."""
    files = list(directory.glob("*.h5"))
    assert len(files) == 1, f"Expected 1 .h5 file, found {len(files)}: {files}"
    return files[0]
