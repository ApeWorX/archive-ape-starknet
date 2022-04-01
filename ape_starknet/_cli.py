import click

from ape_starknet.accounts._cli import accounts


@click.group()
def cli():
    """Starknet ecosystem commands"""


cli.add_command(accounts)  # type: ignore
