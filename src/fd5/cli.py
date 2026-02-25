"""fd5 command-line interface."""

import click


@click.group()
@click.version_option(package_name="fd5")
def cli() -> None:
    """fd5 – Fusion Data Format 5 toolkit."""
