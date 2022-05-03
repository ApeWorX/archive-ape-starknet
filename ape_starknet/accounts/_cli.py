from typing import List, cast

import click
from ape.cli import (
    NetworkBoundCommand,
    Path,
    ape_cli_context,
    existing_alias_argument,
    network_option,
)
from ape.cli.options import ApeCliContextObject
from ape.utils import add_padding_to_strings

from ape_starknet._utils import PLUGIN_NAME
from ape_starknet.accounts import (
    BaseStarknetAccount,
    StarknetAccountContracts,
    StarknetKeyfileAccount,
)


def _get_container(cli_ctx: ApeCliContextObject) -> StarknetAccountContracts:
    return cast(StarknetAccountContracts, cli_ctx.account_manager.containers[PLUGIN_NAME])


@click.group("accounts")
def accounts():
    """Manage Starknet accounts"""


@accounts.command(cls=NetworkBoundCommand)
@ape_cli_context()
@click.argument("alias")
@network_option(ecosystem=PLUGIN_NAME)
@click.option("--token", help="Used for deploying contracts in Alpha MainNet.")
def create(cli_ctx, alias, network, token):
    """Deploy an account"""
    container = _get_container(cli_ctx)

    if alias in container.aliases:
        # Check if we have already deployed in this network.
        # The user will have to delete before they can deploy again.
        existing_account = container.load(alias)
        if existing_account.get_deployment(network):
            cli_ctx.abort(
                f"Account already deployed to '{network}' network. "
                f"Run 'ape starknet accounts delete <alias> --network {network}' "
                "first to re-deploy."
            )

    contract_address = container.deploy_account(alias, token=token)
    contract_address = click.style(contract_address, bold=True)
    cli_ctx.logger.success(f"Account successfully deployed to '{contract_address}'.")


@accounts.command("list")
@ape_cli_context()
def _list(cli_ctx):
    """List your Starknet accounts"""

    starknet_accounts = cast(
        List[StarknetKeyfileAccount], [a for a in _get_container(cli_ctx).accounts]
    )

    if len(starknet_accounts) == 0:
        cli_ctx.logger.warning("No accounts found.")
        return

    num_accounts = len(starknet_accounts)
    header = f"Found {num_accounts} account"
    header += "s" if num_accounts > 1 else ""
    click.echo(f"{header}\n")

    for index in range(num_accounts):
        account = starknet_accounts[index]
        output_dict = {"Alias": account.alias, "Public key": account.address}
        for deployment in account.get_deployments():
            key = f"Contract address ({deployment.network_name})"
            output_dict[key] = deployment.contract_address

        output_keys = add_padding_to_strings([k for k in output_dict.keys()])
        output_dict = {k: output_dict[k.rstrip()] for k in output_keys}

        for k, v in output_dict.items():
            click.echo(f"{k} - {v}")

        if index < num_accounts - 1:
            click.echo()


@accounts.command(name="import")
@ape_cli_context()
@click.argument("alias")
@network_option(ecosystem=PLUGIN_NAME)
@click.option(
    "--address",
    help="The contract address of the account",
    callback=lambda ctx, param, value: ctx.obj.network_manager.starknet.decode_address(value)
    if value
    else None,
)
@click.option("--keyfile", help="Import an existing key-file", type=Path())
def _import(cli_ctx, alias, network, address, keyfile):
    """Add an existing account"""
    container = _get_container(cli_ctx)
    if alias in container.aliases:
        existing_account = container.load(alias)
        if existing_account.get_deployment(network):
            cli_ctx.abort(f"Account already imported with '{network}' network.")

        click.echo(f"Importing existing account to network '{network}'.")
        existing_account.add_deployment(network, address)

    elif keyfile:
        container.import_account_from_key_file(alias, keyfile)
    elif address:
        private_key = click.prompt("Enter private key", hide_input=True)
        container.import_account(alias, network, address, private_key)
    else:
        cli_ctx.abort("Please provide either --keyfile or --address to import this account.")

    cli_ctx.logger.success(f"Import account '{alias}'.")


@accounts.command()
@ape_cli_context()
@existing_alias_argument(account_type=BaseStarknetAccount)
@network_option(ecosystem=PLUGIN_NAME)
def delete(cli_ctx, alias, network):
    """Delete an existing account"""
    container = _get_container(cli_ctx)

    if network == "starknet":
        # Did not specify a network and should use normally use default
        # However, if the account only exists on a single network, assume that one.
        account = container.load(alias)
        deployments = account.get_deployments()
        if len(deployments) == 1:
            network = deployments[0].network_name

    container.delete_account(alias, network=network)
    cli_ctx.logger.success(f"Account '{alias}' on network '{network}' has been deleted.")


@accounts.command()
@ape_cli_context()
@existing_alias_argument(account_type=StarknetKeyfileAccount)
def change_password(cli_ctx, alias):
    """Change the password of an existing account"""
    account = cli_ctx.account_manager.load(alias)
    account.change_password()
    cli_ctx.logger.success(f"Password has been changed for account '{alias}'")
