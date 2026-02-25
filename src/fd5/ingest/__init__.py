"""fd5.ingest — loader protocol, shared ingest helpers, and metadata import."""

from fd5.ingest._base import Loader, discover_loaders, hash_source_files
from fd5.ingest.metadata import (
    load_datacite_metadata,
    load_metadata,
    load_rocrate_metadata,
)

__all__ = [
    "Loader",
    "discover_loaders",
    "hash_source_files",
    "load_datacite_metadata",
    "load_metadata",
    "load_rocrate_metadata",
]
