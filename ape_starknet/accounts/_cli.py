from typing import List, cast

import click
from ape.cli import NetworkBoundCommand, ape_cli_context, existing_alias_argument, network_option
from ape.cli.options import ApeCliContextObject
from ape.utils import add_padding_to_strings

from ape_starknet._utils import PLUGIN_NAME
from ape_starknet.accounts import StarknetAccount, StarknetAccountContracts


def _get_container(cli_ctx: ApeCliContextObject) -> StarknetAccountContracts:
    return cast(StarknetAccountContracts, cli_ctx.account_manager.containers[PLUGIN_NAME])


@click.group("accounts")
def accounts():
    """Manage Starknet accounts"""


@accounts.command(cls=NetworkBoundCommand)
@ape_cli_context()
@click.argument("alias")
@network_option(ecosystem=PLUGIN_NAME)
def create(cli_ctx, alias, network):
    """Deploy an account."""
    container = _get_container(cli_ctx)

    if alias in container.aliases:
        # Check if we have already deployed in this network.
        # The user will have to delete before they can deploy again.
        existing_account = container.load(alias)
        if network in [d.network_name for d in existing_account.deployments]:
            cli_ctx.abort(
                f"Account already deployed to '{network}' network. "
                f"Run 'ape starknet accounts delete <alias> --network {PLUGIN_NAME}:{network}' "
                "first to re-deploy."
            )

    contract_address = container.deploy_account(alias)
    contract_address = click.style(contract_address, bold=True)
    cli_ctx.logger.success(f"Account successfully deployed to '{contract_address}'.")


@accounts.command("list")
@ape_cli_context()
def _list(cli_ctx):
    """List your Starknet accounts"""

    starknet_accounts = cast(List[StarknetAccount], [a for a in _get_container(cli_ctx).accounts])

    if len(starknet_accounts) == 0:
        cli_ctx.logger.warning("No accounts found.")
        return

    num_accounts = len(starknet_accounts)
    header = f"Found {num_accounts} account"
    header += "s" if num_accounts > 1 else ""
    click.echo(f"{header}\n")

    for index in range(num_accounts):
        account = starknet_accounts[index]
        click.echo(f"{account.alias}:")
        output_dict = {"Public key": account.address}
        for deployment in account.deployments:
            key = f"{deployment.network_name.capitalize()} network address"
            output_dict[key] = deployment.contract_address

        output_keys = add_padding_to_strings([k for k in output_dict.keys()])
        output_dict = {k: output_dict[k.rstrip()] for k in output_keys}

        for k, v in output_dict.items():
            click.echo(f"{k}:{v}")

        if index < num_accounts - 1:
            click.echo()


@accounts.command(short_help="Delete an existing account")
@existing_alias_argument(account_type=StarknetAccount)
@ape_cli_context()
def delete(cli_ctx, alias):
    account = cli_ctx.account_manager.load(alias)
    account.delete()
    cli_ctx.logger.success(f"Account '{alias}' has been deleted")
