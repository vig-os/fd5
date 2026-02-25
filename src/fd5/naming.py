"""Filename generation following the fd5 naming convention.

See white-paper.md § File Naming Convention.
"""

from __future__ import annotations

from datetime import datetime

_SHA256_PREFIX = "sha256:"
_ID_HEX_LENGTH = 8
_EXTENSION = ".h5"
_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"


def generate_filename(
    product: str,
    id_hash: str,
    timestamp: datetime | None,
    descriptors: list[str],
) -> str:
    """Generate an fd5-compliant filename.

    Format: ``YYYY-MM-DD_HH-MM-SS_<product>-<id>_<descriptors>.h5``

    When *timestamp* is ``None`` the datetime prefix is omitted.
    The *id_hash* is truncated to the first 8 hex characters; a
    ``sha256:`` prefix is stripped automatically if present.
    """
    short_id = _truncate_id(id_hash)
    parts: list[str] = []

    if timestamp is not None:
        parts.append(timestamp.strftime(_TIMESTAMP_FORMAT))

    parts.append(f"{product}-{short_id}")
    parts.extend(descriptors)

    return "_".join(parts) + _EXTENSION


def _truncate_id(id_hash: str) -> str:
    raw = id_hash.removeprefix(_SHA256_PREFIX)
    return raw[:_ID_HEX_LENGTH]
