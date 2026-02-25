"""fd5.schema — embed, validate, dump, and generate JSON Schema for fd5 files.

Stores ``_schema`` as a JSON string attribute at file root for single-read
self-description (see white-paper.md § 9).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import jsonschema
import numpy as np

from fd5.h5io import h5_to_dict
from fd5.registry import get_schema


def embed_schema(
    file: h5py.File,
    schema_dict: dict[str, Any],
    *,
    schema_version: int = 1,
) -> None:
    """Write ``_schema`` (JSON string) and ``_schema_version`` (int) to *file* root."""
    file.attrs["_schema"] = json.dumps(schema_dict, separators=(",", ":"))
    file.attrs["_schema_version"] = np.int64(schema_version)


def dump_schema(path: str | Path) -> dict[str, Any]:
    """Extract and parse the ``_schema`` attribute from an fd5 file.

    Raises:
        KeyError: If the file has no ``_schema`` attribute.
        json.JSONDecodeError: If the stored string is not valid JSON.
    """
    with h5py.File(path, "r") as f:
        raw = f.attrs["_schema"]
    return json.loads(raw)


def validate(path: str | Path) -> list[jsonschema.ValidationError]:
    """Validate file structure against its embedded JSON Schema.

    Returns a list of :class:`jsonschema.ValidationError` — empty when valid.

    Raises:
        KeyError: If the file has no ``_schema`` attribute.
    """
    with h5py.File(path, "r") as f:
        raw = f.attrs["_schema"]
        schema_dict = json.loads(raw)
        instance = h5_to_dict(f)

    validator = jsonschema.Draft202012Validator(schema_dict)
    return list(validator.iter_errors(instance))


def generate_schema(product_type: str) -> dict[str, Any]:
    """Produce a JSON Schema Draft 2020-12 document for *product_type*.

    Delegates to the product schema registry.

    Raises:
        ValueError: If *product_type* is not registered.
    """
    product_schema = get_schema(product_type)
    return product_schema.json_schema()
