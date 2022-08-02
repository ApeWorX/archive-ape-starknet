import json
import random
import tempfile
from pathlib import Path

import pytest

from ape_starknet.utils import get_random_private_key

from ..conftest import CONTRACT_ADDRESS, EXISTING_KEY_FILE_ALIAS, PASSWORD
from .conftest import ApeStarknetCliRunner


@pytest.fixture(scope="module")
def accounts_runner(ape_cli):
    return ApeStarknetCliRunner(ape_cli, ["starknet", "accounts"])


@pytest.fixture(scope="module")
def root_accounts_runner(ape_cli):
    return ApeStarknetCliRunner(ape_cli, ["accounts"])


@pytest.fixture(scope="module")
def argent_x_backup(argent_x_key_file_account_data):
    with tempfile.TemporaryDirectory() as temp_dir:
        key_file_path = Path(temp_dir) / "argent-x-backup.json"
        key_file_path.write_text(json.dumps(argent_x_key_file_account_data))
        yield key_file_path


def test_create(accounts_runner):
    """
    Integration test for accounts.
    It all happens under one test because it is really slow to deploy accounts.
    """

    random_alias = "".join(random.choice(["a", "b", "c", "d", "e", "f"]) for _ in range(6))
    output = accounts_runner.invoke("create", random_alias)
    assert "Account successfully deployed to" in output


def test_delete(accounts_runner, key_file_account):
    """
    This integration test deletes a single deployment of an account and then
    re-import it. The account never completely goes away because it is deployed on
    multiple networks.
    """
    output = accounts_runner.invoke(
        "delete",
        EXISTING_KEY_FILE_ALIAS,
        "--network",
        "starknet:testnet",
        input=PASSWORD,
    )
    assert EXISTING_KEY_FILE_ALIAS in output
    output = accounts_runner.invoke("list")

    # The account should still have a remaining deployment and thus still found in output
    assert EXISTING_KEY_FILE_ALIAS in output

    # Only the testnet deployment should have gotten deleted
    output_lines = output.split("\n")
    for index in range(len(output_lines)):
        line = output_lines[index]
        if EXISTING_KEY_FILE_ALIAS not in line:
            continue

        # Find the deployments parts
        next_index = index + 1
        for next_line in output_lines[next_index:]:
            if not next_line.strip():
                break  # Reached end of account's section

            if next_line.startswith("Contract address (testnet)"):
                assert CONTRACT_ADDRESS not in next_line, "Deployment failed to delete"

    # Re-import the deployment (clean-up)
    accounts_runner.invoke(
        "import",
        EXISTING_KEY_FILE_ALIAS,
        "--network",
        "starknet:testnet",
        "--address",
        CONTRACT_ADDRESS,
        input=PASSWORD,
    )


@pytest.mark.parametrize(
    "private_key",
    (
        get_random_private_key(),
        "0x0097a6a4998e2eb47d4cea623c9f8b3048764fc38a92616bdf1c3e68be8b5e28",
        267944034277627769235577208827196223019601239705086925741947749358138777128,
    ),
)
def test_import(accounts_runner, key_file_account, account_container, private_key):
    network = "starknet:testnet"  # NOTE: Does not actually connect
    account_path = account_container.data_folder / f"{EXISTING_KEY_FILE_ALIAS}.json"
    address = key_file_account.address

    if account_path.is_file():
        # Corrupted from previous test
        account_path.unlink()

    accounts_runner.invoke(
        "import",
        EXISTING_KEY_FILE_ALIAS,
        "--network",
        network,
        "--address",
        address,
        input=[private_key, PASSWORD, PASSWORD],
    )

    # Clean-up
    accounts_runner.invoke(
        "delete",
        EXISTING_KEY_FILE_ALIAS,
        "--network",
        network,
        input=[PASSWORD, "y"],
    )


def test_import_argent_x_key_file(accounts_runner, argent_x_backup, account_container):
    alias = "__TEST_ARGENT_X_BACKUP__"
    account_path = account_container.data_folder / f"{alias}.json"

    if account_path.is_file():
        # Corrupted from previous test
        account_path.unlink()

    output = accounts_runner.invoke(
        "import",
        alias,
        "--keyfile",
        str(argent_x_backup),
        "--network",
        "starknet:testnet",
        input=PASSWORD,
    )
    assert "SUCCESS" in output
    account_path.unlink()


def test_import_when_local(accounts_runner):
    output = accounts_runner.invoke(
        "import",
        "FAILS",
        "--address",
        "0x0098580e36aB1485C66f0DC95C2c923e734B7Af44D04dD2B5b9d0809Aa672033",
        ensure_successful=False,
    )
    assert "ERROR: Must use --network option to specify non-local network." in output


def test_list(accounts_runner, key_file_account):
    assert EXISTING_KEY_FILE_ALIAS in accounts_runner.invoke("list")


def test_core_accounts_list_all(root_accounts_runner, key_file_account):
    # This is making sure the normal `ape accounts list --all` command works.
    assert EXISTING_KEY_FILE_ALIAS in root_accounts_runner.invoke("list", "--all")


def test_change_password(accounts_runner, key_file_account):
    new_password = "321"
    assert "SUCCESS" in accounts_runner.invoke(
        "change-password", EXISTING_KEY_FILE_ALIAS, input=[PASSWORD, new_password, new_password]
    )
    assert "SUCCESS" in accounts_runner.invoke(
        "change-password", EXISTING_KEY_FILE_ALIAS, input=[new_password, PASSWORD, PASSWORD]
    )
