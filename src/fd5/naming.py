"""Filename generation following the fd5 naming convention.

See docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5naming--filename-generation
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

_TIMESTAMP_FMT = "%Y-%m-%d_%H-%M-%S"
_HASH_DISPLAY_LEN = 8


def generate_filename(
    product: str,
    id_hash: str,
    timestamp: datetime | None = None,
    descriptors: Sequence[str] = (),
) -> str:
    """Generate an fd5-convention filename.

    Format: ``YYYY-MM-DD_HH-MM-SS_<product>-<id>_<descriptors>.h5``

    Products without a timestamp omit the datetime prefix.
    """
    if not product:
        raise ValueError("product must be a non-empty string")

    if ":" not in id_hash:
        raise ValueError("id_hash must include an algorithm prefix (e.g. 'sha256:...')")

    hex_part = id_hash.split(":", 1)[1]
    if not hex_part:
        raise ValueError("id_hash must contain hex characters after the prefix")

    short_id = hex_part[:_HASH_DISPLAY_LEN]

    parts: list[str] = []

    if timestamp is not None:
        parts.append(timestamp.strftime(_TIMESTAMP_FMT))

    parts.append(f"{product}-{short_id}")
    parts.extend(descriptors)

    return "_".join(parts) + ".h5"
