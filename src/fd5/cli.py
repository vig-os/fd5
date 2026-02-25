"""fd5 command-line interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import h5py

from fd5.hash import verify
from fd5.manifest import write_manifest
from fd5.rocrate import write as write_rocrate
from fd5.schema import dump_schema, validate


@click.group()
@click.version_option(package_name="fd5")
def cli() -> None:
    """fd5 – Fusion Data Format 5 toolkit."""


@cli.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
def validate_cmd(file: str) -> None:
    """Validate an fd5 file against its embedded schema and content_hash."""
    path = Path(file)
    errors: list[str] = []

    try:
        schema_errors = validate(path)
    except KeyError:
        click.echo("Error: file has no embedded _schema attribute.", err=True)
        sys.exit(1)

    for err in schema_errors:
        errors.append(f"Schema: {err.message}")

    if not verify(path):
        errors.append("Integrity: content_hash mismatch or missing.")

    if errors:
        for msg in errors:
            click.echo(msg, err=True)
        sys.exit(1)

    click.echo("OK – schema valid, content_hash verified.")


# click registers the command name from the function; override with the decorator
validate_cmd.name = "validate"


@cli.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
def info(file: str) -> None:
    """Print file metadata: root attrs and dataset shapes."""
    path = Path(file)

    with h5py.File(path, "r") as f:
        click.echo(f"File: {path.name}")

        for key in sorted(f.attrs.keys()):
            click.echo(f"  {key}: {_format_attr(f.attrs[key])}")

        datasets = _collect_datasets(f)
        if datasets:
            click.echo("Datasets:")
            for ds_path, shape, dtype in datasets:
                click.echo(f"  {ds_path}: shape={shape}, dtype={dtype}")


@cli.command("schema-dump")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
def schema_dump(file: str) -> None:
    """Extract and pretty-print the embedded JSON Schema."""
    path = Path(file)
    try:
        schema_dict = dump_schema(path)
    except KeyError:
        click.echo("Error: file has no embedded _schema attribute.", err=True)
        sys.exit(1)

    click.echo(json.dumps(schema_dict, indent=2))


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output path for manifest.toml (default: <directory>/manifest.toml).",
)
def manifest(directory: str, output: str | None) -> None:
    """Generate manifest.toml from fd5 files in a directory."""
    dir_path = Path(directory)
    out_path = Path(output) if output else dir_path / "manifest.toml"
    write_manifest(dir_path, out_path)
    click.echo(f"Wrote {out_path}")


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output path for datacite.yml (default: <directory>/datacite.yml).",
)
def datacite(directory: str, output: str | None) -> None:
    """Generate datacite.yml from manifest.toml in a directory."""
    from fd5.datacite import write as datacite_write

    dir_path = Path(directory)
    manifest_path = dir_path / "manifest.toml"
    if not manifest_path.is_file():
        click.echo(f"Error: {manifest_path} not found.", err=True)
        sys.exit(1)
    out_path = Path(output) if output else dir_path / "datacite.yml"
    datacite_write(manifest_path, out_path)
    click.echo(f"Wrote {out_path}")



@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output path for ro-crate-metadata.json (default: <directory>/ro-crate-metadata.json).",
)
def rocrate(directory: str, output: str | None) -> None:
    """Generate ro-crate-metadata.json from fd5 files in a directory."""
    dir_path = Path(directory)
    out_path = Path(output) if output else None
    write_rocrate(dir_path, out_path)
    written = out_path or dir_path / "ro-crate-metadata.json"
    click.echo(f"Wrote {written}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_attr(value: object) -> str:
    import numpy as np

    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.generic):
        return str(value.item())
    return str(value)


def _collect_datasets(
    group: h5py.Group, prefix: str = ""
) -> list[tuple[str, tuple[int, ...], str]]:
    results: list[tuple[str, tuple[int, ...], str]] = []
    for key in sorted(group.keys()):
        item = group[key]
        full_path = f"{prefix}/{key}" if prefix else key
        if isinstance(item, h5py.Dataset):
            results.append((full_path, item.shape, str(item.dtype)))
        elif isinstance(item, h5py.Group):
            results.extend(_collect_datasets(item, full_path))
    return results
