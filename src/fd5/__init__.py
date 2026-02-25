"""fd5 - A new Python project."""

__version__ = "0.1.0"

from fd5.create import create
from fd5.hash import verify
from fd5.migrate import migrate
from fd5.naming import generate_filename
from fd5.schema import validate

__all__ = ["create", "generate_filename", "migrate", "validate", "verify"]
