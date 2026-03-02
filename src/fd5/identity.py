"""fd5.identity -- author identity management for audit trail entries.

Stores the current user identity in ``~/.fd5/identity.toml`` and provides
a fall-back anonymous identity when no configuration file exists.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

_VALID_TYPES = frozenset({"orcid", "anonymous", "local"})
_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
_DEFAULT_CONFIG_DIR = Path.home() / ".fd5"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Identity:
    """An author identity for audit log entries."""

    type: str
    id: str
    name: str

    def to_dict(self) -> dict[str, str]:
        """Serialise to a JSON/TOML-compatible dict."""
        return {"type": self.type, "id": self.id, "name": self.name}


def _anonymous() -> Identity:
    """Return the default anonymous identity."""
    return Identity(type="anonymous", id="", name="Anonymous")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_identity(identity: Identity) -> None:
    """Raise :class:`ValueError` if *identity* is structurally invalid."""
    if identity.type not in _VALID_TYPES:
        raise ValueError(
            f"Unknown identity type {identity.type!r}; "
            f"valid types are {sorted(_VALID_TYPES)}"
        )
    if identity.type == "orcid" and not _ORCID_RE.match(identity.id):
        raise ValueError(
            f"ORCID id {identity.id!r} does not match NNNN-NNNN-NNNN-NNNX pattern"
        )


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------


def load_identity(*, config_dir: Path | None = None) -> Identity:
    """Load identity from ``identity.toml`` in *config_dir*.

    Returns an anonymous identity when the file does not exist.
    """
    import tomllib

    config_dir = config_dir or _DEFAULT_CONFIG_DIR
    toml_path = config_dir / "identity.toml"

    if not toml_path.is_file():
        return _anonymous()

    data: dict[str, Any] = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    return Identity(
        type=data.get("type", "anonymous"),
        id=data.get("id", ""),
        name=data.get("name", "Anonymous"),
    )


def save_identity(
    identity: Identity,
    *,
    config_dir: Path | None = None,
) -> None:
    """Persist *identity* to ``identity.toml`` in *config_dir*."""
    import tomli_w

    config_dir = config_dir or _DEFAULT_CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)

    toml_path = config_dir / "identity.toml"
    toml_path.write_bytes(tomli_w.dumps(identity.to_dict()).encode("utf-8"))
