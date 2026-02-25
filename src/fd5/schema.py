"""fd5.schema — embed, validate, dump, and generate JSON Schema for fd5 files."""

from __future__ import annotations


def embed_schema(file, schema_dict, *, schema_version=1):
    raise NotImplementedError


def dump_schema(path):
    raise NotImplementedError


def validate(path):
    raise NotImplementedError


def generate_schema(product_type):
    raise NotImplementedError
