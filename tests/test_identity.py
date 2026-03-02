"""Tests for fd5.identity -- identity data model, load/save from TOML config."""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def identity_dir(tmp_path: Path) -> Path:
    """Return a temp directory to act as ~/.fd5/."""
    return tmp_path / ".fd5"


# ---------------------------------------------------------------------------
# Identity dataclass
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_create_identity(self):
        from fd5.identity import Identity

        ident = Identity(type="orcid", id="0000-0001-2345-6789", name="Lars Gerchow")
        assert ident.type == "orcid"
        assert ident.id == "0000-0001-2345-6789"
        assert ident.name == "Lars Gerchow"

    def test_to_dict(self):
        from fd5.identity import Identity

        ident = Identity(type="orcid", id="0000-0001-2345-6789", name="Lars")
        d = ident.to_dict()
        assert d == {"type": "orcid", "id": "0000-0001-2345-6789", "name": "Lars"}

    def test_anonymous_identity(self):
        from fd5.identity import Identity

        ident = Identity(type="anonymous", id="", name="Anonymous")
        assert ident.type == "anonymous"
        assert ident.id == ""


# ---------------------------------------------------------------------------
# load_identity / save_identity
# ---------------------------------------------------------------------------


class TestLoadIdentity:
    def test_load_missing_file_returns_anonymous(self, identity_dir: Path):
        """When identity.toml does not exist, return anonymous identity."""
        from fd5.identity import load_identity

        ident = load_identity(config_dir=identity_dir)
        assert ident.type == "anonymous"
        assert ident.name == "Anonymous"

    def test_load_valid_toml(self, identity_dir: Path):
        """Load a properly formatted identity.toml file."""
        from fd5.identity import load_identity

        identity_dir.mkdir(parents=True, exist_ok=True)
        toml_content = """\
type = "orcid"
id = "0000-0001-2345-6789"
name = "Lars Gerchow"
"""
        (identity_dir / "identity.toml").write_text(toml_content)
        ident = load_identity(config_dir=identity_dir)
        assert ident.type == "orcid"
        assert ident.id == "0000-0001-2345-6789"
        assert ident.name == "Lars Gerchow"

    def test_save_load_roundtrip(self, identity_dir: Path):
        """Identity saved with save_identity can be loaded back."""
        from fd5.identity import Identity, load_identity, save_identity

        original = Identity(type="orcid", id="0000-0001-2345-6789", name="Lars Gerchow")
        save_identity(original, config_dir=identity_dir)
        loaded = load_identity(config_dir=identity_dir)
        assert loaded.type == original.type
        assert loaded.id == original.id
        assert loaded.name == original.name

    def test_save_creates_directory(self, identity_dir: Path):
        """save_identity creates the config directory if it doesn't exist."""
        from fd5.identity import Identity, save_identity

        assert not identity_dir.exists()
        ident = Identity(type="orcid", id="0000-0001-2345-6789", name="Lars")
        save_identity(ident, config_dir=identity_dir)
        assert identity_dir.exists()
        assert (identity_dir / "identity.toml").exists()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestIdentityValidation:
    def test_identity_type_validation(self):
        """Only known identity types are accepted."""
        from fd5.identity import Identity, validate_identity

        ident = Identity(type="invalid_type", id="abc", name="Test")
        with pytest.raises(ValueError, match="type"):
            validate_identity(ident)

    def test_valid_types_accepted(self):
        """Known types should not raise."""
        from fd5.identity import Identity, validate_identity

        ids = {
            "orcid": "0000-0001-2345-6789",
            "anonymous": "",
            "local": "user@host",
        }
        for t in ("orcid", "anonymous", "local"):
            ident = Identity(type=t, id=ids[t], name="Test")
            validate_identity(ident)  # should not raise

    def test_orcid_format_validation(self):
        """ORCID IDs must match the NNNN-NNNN-NNNN-NNNN pattern."""
        from fd5.identity import Identity, validate_identity

        bad_orcid = Identity(type="orcid", id="not-an-orcid", name="Test")
        with pytest.raises(ValueError, match="ORCID"):
            validate_identity(bad_orcid)

    def test_orcid_valid_format_accepted(self):
        """A properly formatted ORCID should not raise."""
        from fd5.identity import Identity, validate_identity

        ident = Identity(type="orcid", id="0000-0001-2345-6789", name="Test")
        validate_identity(ident)  # should not raise

    def test_orcid_format_with_x_checksum(self):
        """ORCID IDs can have X as the final check digit."""
        from fd5.identity import Identity, validate_identity

        ident = Identity(type="orcid", id="0000-0001-2345-678X", name="Test")
        validate_identity(ident)  # should not raise
