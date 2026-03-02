"""fd5.ingest — loader protocol and shared ingest helpers."""

from fd5.ingest._base import Loader, discover_loaders, hash_source_files

__all__ = ["Loader", "discover_loaders", "hash_source_files"]
