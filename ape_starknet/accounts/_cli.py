import json
from typing import List, Optional, Union, cast

import click
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.cli import ape_cli_context, existing_alias_argument, non_existing_alias_argument
from ape.cli.options import ApeCliContextObject
from ape.logging import logger
from ape.utils import add_padding_to_strings
from eth_keyfile import decode_keyfile_json
from eth_utils import is_hex, text_if_str, to_bytes, to_hex
from hexbytes import HexBytes
from starkware.crypto.signature.signature import EC_ORDER
from starkware.starknet.definitions.fields import ContractAddressSalt

from ape_starknet.accounts import (
    BaseStarknetAccount,
    StarknetAccountContainer,
    StarknetAccountDeployment,
    StarknetKeyfileAccount,
)
from ape_starknet.ecosystems import NETWORKS
from ape_starknet.utils import (
    ARGENTX_ACCOUNT_CLASS_HASH,
    OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH,
    PLUGIN_NAME,
    to_int,
)


def _get_container(cli_ctx: ApeCliContextObject) -> StarknetAccountContainer:
    return cast(StarknetAccountContainer, cli_ctx.account_manager.containers[PLUGIN_NAME])


def class_hash_option(default: Optional[Union[str, int]] = None, required: bool = False):
    def callback(ctx, param, value) -> Optional[int]:
        if value is None:
            return None

        elif isinstance(value, int):
            return int(value)

        elif value.lower() == "openzeppelin":
            return OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH

        elif value.lower() in ("argentx", "argent-x"):
            return ARGENTX_ACCOUNT_CLASS_HASH

        return to_int(value)

    return click.option(
        "--class-hash",
        help="The class hash of the account contract.",
        required=required,
        callback=callback,
        default=default,
        type=str,
    )


def address_option():
    return click.option(
        "--address",
        help="The contract address of the account",
        callback=lambda ctx, param, value: ctx.obj.network_manager.starknet.decode_address(value)
        if value
        else None,
    )


def _network_callback(ctx, param, value, single: bool = False):
    parse = ctx.obj.network_manager.parse_network_choice

    if single and value == "starknet":
        raise click.BadOptionUsage("--network", "Must use single network.")

    elif value == "starknet":
        # Use all live networks.
        return [_validate_network(parse, n) for n in NETWORKS]

    if single and value is not None:
        return _validate_network(parse, value)

    elif single:
        return value

    elif value is not None:
        return [_validate_network(parse, n.strip()) for n in value.split(",")]

    return []


def network_option(required: bool = False, default: Optional[str] = None, single: bool = False):
    def callback(ctx, param, value):
        return _network_callback(ctx, param, value, single=single)

    return click.option(
        "--network",
        default=default,
        required=required,
        callback=callback,
    )


@click.group("accounts")
def accounts():
    """Manage Starknet accounts"""


def _salt_callback(ctx, param, value):
    return value or ContractAddressSalt.get_random_value()


@accounts.command()
@ape_cli_context()
@non_existing_alias_argument()
@class_hash_option(default=OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH)
@click.option(
    "--constructor-calldata", help="Comma separated list of calldata, default tries to be smart."
)
@click.option(
    "--salt", help="The default address salt to use when deploying.", callback=_salt_callback
)
def create(cli_ctx, alias, class_hash, constructor_calldata, salt):
    """Create an account keypair"""
    calldata = (
        [cli_ctx.starknet.decode_primitive_value(x) for x in constructor_calldata.split(",")]
        if constructor_calldata is not None
        else None
    )
    _get_container(cli_ctx).create_account(
        alias,
        class_hash=class_hash,
        constructor_calldata=calldata,
        salt=salt,
        allow_local_file_store=True,
    )
    cli_ctx.logger.success(f"Created account key-pair for alias '{alias}'.")


def _funder_callback(ctx, param, value):
    container = _get_container(ctx.obj)
    if not value:
        return None

    if value.isnumeric():
        # Useful for testing / local but not realistic.
        return container.genesis_test_accounts[int(value)]

    return container.load(value)


@accounts.command()
@ape_cli_context()
@click.argument("alias")
@network_option(default=LOCAL_NETWORK_NAME, single=True)
@click.option("--funder", help="Use another an account to help fund", callback=_funder_callback)
def deploy(cli_ctx, network, alias, funder):
    """Deploy an account"""
    with cli_ctx.network_manager.parse_network_choice(network):
        logger.info(f"Deploying account '{alias}' to network '{network}'.")
        container = _get_container(cli_ctx)
        account = container.load(alias)
        uses_keyfile = isinstance(account, StarknetKeyfileAccount)

        if uses_keyfile:
            account.unlock("Enter passphrase to deploy account")  # type: ignore[attr-defined]

        try:
            receipt = account.deploy_account(funder=funder)
            contract_address_styled = click.style(receipt.contract_address, bold=True)
            logger.success(f"Account successfully deployed to '{contract_address_styled}'.")
        finally:
            if uses_keyfile:
                account.lock()  # type: ignore[attr-defined]


@accounts.command("list")
@ape_cli_context()
def _list(cli_ctx):
    """List your Starknet accounts"""

    starknet_accounts: List[StarknetKeyfileAccount] = [
        x for x in _get_container(cli_ctx).accounts if isinstance(x, StarknetKeyfileAccount)
    ]

    if len(starknet_accounts) == 0:
        cli_ctx.logger.info("No accounts found.")
        return

    num_accounts = len(starknet_accounts)
    header = f"Found {num_accounts} account"
    header += "s" if num_accounts > 1 else ""
    click.echo(f"{header}\n")

    for index in range(num_accounts):
        account = starknet_accounts[index]
        output_dict = {
            "Alias": account.alias,
            "Public key": account.public_key,
            "Class hash": to_hex(account.class_hash),
        }
        if not account.deployments:
            output_dict["Contract address (not deployed)"] = account.address

        else:
            for deployment in account.deployments:
                key = f"Contract address ({deployment.network_name})"
                output_dict[key] = deployment.contract_address

        output_keys = add_padding_to_strings(list(output_dict.keys()))
        output_dict = {k: output_dict[k.rstrip()] for k in output_keys}

        for k, v in output_dict.items():
            click.echo(f"{k} - {v}")

        if index < num_accounts - 1:
            click.echo()


def _validate_network(parse, network: str) -> str:
    # Temporarily connect to extract network name and validate network.
    live_nets = list(NETWORKS.keys())
    options = [*live_nets, LOCAL_NETWORK_NAME]

    if network.startswith("starknet:"):
        network = network.replace("starknet:", "")

    if network not in options:
        options_str = ",".join(options)
        raise click.BadOptionUsage("--network", f"Network '{network}' not one of '{options_str}'.")

    return f"starknet:{network}"


@accounts.command(name="import")
@ape_cli_context()
@click.argument("alias")
@network_option(required=True)
@address_option()
@class_hash_option()
@click.option("--salt", help="The contract address salt used when deploying the contract.")
def _import(cli_ctx, alias, network, address, class_hash, salt):
    """Add an existing, deployed account"""

    container = _get_container(cli_ctx)
    if alias in container.aliases:
        # Since the alias exists, try to import as a new deployment.

        existing_account = container.load(alias)
        if not isinstance(existing_account, StarknetKeyfileAccount):
            cli_ctx.abort(
                "Unable to use default ape-starknet CLI to add "
                "deployments to accounts from other plugins. "
                f"Try using plugin with account type {type(existing_account).__name__}."
            )

        else:
            # Assume calculated address if not given anything.
            address = address or existing_account.address
            if not salt and address == existing_account.address:
                # It must have used the same salt since the addresses are the same.
                salt = existing_account.salt

            networks_str = ", ".join(network)
            click.echo(f"Importing existing account on network(s) '{networks_str}'.")
            for network_name in network:
                existing_account.add_deployment(network_name, address, salt, leave_unlocked=False)

    elif address and not class_hash:
        cli_ctx.abort("--class-hash is required when importing an account for the first time.")

    elif address:
        # Account is being imported for the first time.
        private_key = click.prompt(f"Enter private key for '{alias}'", hide_input=True).strip()

        if private_key.isnumeric():
            # NOTE: Check base 10 before 16 because is_hex("123") is True.
            private_key = int(private_key)
        elif is_hex(private_key):
            private_key = int(private_key, 16)
        else:
            cli_ctx.abort("Invalid private key. Expecting numeric value.")

        if private_key < 1 or private_key >= EC_ORDER:
            cli_ctx.abort("Private key not in range [1, EC_ORDER).")

        deployments = [
            StarknetAccountDeployment(contract_address=address, network_name=n, salt=salt)
            for n in network
        ]
        container.import_account(alias, class_hash, private_key, salt=salt, deployments=deployments)

    else:
        cli_ctx.abort("--address required when importing and account for the first time.")

    cli_ctx.logger.success(f"Imported account '{alias}'.")


@accounts.command(short_help="Export an account private key")
@ape_cli_context()
@existing_alias_argument(account_type=StarknetKeyfileAccount)
def export(cli_ctx, alias):
    account = cast(StarknetKeyfileAccount, _get_container(cli_ctx).load(alias))
    path = account.key_file_path
    account_json = json.loads(path.read_text())
    passphrase = click.prompt("Enter password to decrypt account", hide_input=True)
    passphrase_bytes = text_if_str(to_bytes, passphrase)
    decoded_json = HexBytes(decode_keyfile_json(account_json, passphrase_bytes))
    private_key = to_int(decoded_json.hex())
    cli_ctx.logger.success(
        f"Account {account.alias} private key: {click.style(private_key, bold=True)})"
    )


@accounts.command()
@ape_cli_context()
@existing_alias_argument(account_type=BaseStarknetAccount)
@network_option()
@address_option()
def delete(cli_ctx, alias, network, address):
    """Delete an existing account deployment"""
    container = _get_container(cli_ctx)
    account = container.load(alias)
    deployments_before = len(account.deployments)
    container.delete_account(alias, networks=network, address=address, leave_unlocked=False)

    if account.address_int not in container:
        cli_ctx.logger.success(f"Account '{alias}' deleted.")
    elif (len(account.deployments) < deployments_before) and network:
        choices_str = ",".join([x.replace("starknet:", "") for x in network])
        cli_ctx.logger.success(f"Account '{alias}' deployments on network '{choices_str}' deleted.")


@accounts.command()
@ape_cli_context()
@existing_alias_argument(account_type=StarknetKeyfileAccount)
def change_password(cli_ctx, alias):
    """Change the password of an existing account"""
    account = cli_ctx.account_manager.load(alias)
    account.change_password(leave_unlocked=False)
    cli_ctx.logger.success(f"Password has been changed for account '{alias}'")
