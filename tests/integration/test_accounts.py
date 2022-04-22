import json
import tempfile
from pathlib import Path

import pytest

from ..conftest import ALIAS, CONTRACT_ADDRESS, EXISTING_KEY_FILE_ALIAS, PASSWORD
from .conftest import ApeStarknetCliRunner

NEW_ALIAS = f"{ALIAS}new"


@pytest.fixture
def accounts_runner(ape_cli):
    return ApeStarknetCliRunner(ape_cli, ["starknet", "accounts"])


@pytest.fixture
def root_accounts_runner(ape_cli):
    return ApeStarknetCliRunner(ape_cli, ["accounts"])


@pytest.fixture
def deployed_account(account_container):
    account_container.deploy_account(NEW_ALIAS)
    yield account_container.load(NEW_ALIAS)
    account_container.delete_account(NEW_ALIAS)


@pytest.fixture
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

    output = accounts_runner.invoke("create", NEW_ALIAS)
    assert "Account successfully deployed to" in output
    output = accounts_runner.invoke("list")
    assert NEW_ALIAS in output

    # Delete newly created account (clean-up)
    accounts_runner.invoke("delete", NEW_ALIAS)


def test_delete(accounts_runner, existing_key_file_account):
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
        input=f"{PASSWORD}\n",
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
        input=f"{PASSWORD}\n",
    )


def test_import(accounts_runner, existing_key_file_account, account_container):
    network = "starknet:testnet"  # NOTE: Does not actually connect
    account_path = account_container.data_folder / f"{NEW_ALIAS}.json"

    if account_path.is_file():
        # Corrupted from previous test
        account_path.unlink()

    private_key = str(CONTRACT_ADDRESS)
    valid_input = f"{private_key}\n{PASSWORD}\n{PASSWORD}"
    accounts_runner.invoke(
        "import",
        NEW_ALIAS,
        "--network",
        network,
        "--address",
        CONTRACT_ADDRESS,
        input=valid_input,
    )

    # Clean-up
    accounts_runner.invoke(
        "delete",
        NEW_ALIAS,
        "--network",
        network,
        input=f"{PASSWORD}\ny\n",
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
        input=f"{PASSWORD}\n",
    )
    assert "SUCCESS" in output
    account_path.unlink()


def test_list(accounts_runner, existing_key_file_account):
    assert EXISTING_KEY_FILE_ALIAS in accounts_runner.invoke("list")


def test_core_accounts_list_all(root_accounts_runner, existing_key_file_account):
    # This is making sure the normal `ape accounts list --all` command works.
    assert EXISTING_KEY_FILE_ALIAS in root_accounts_runner.invoke("list", "--all")


def test_change_password(accounts_runner, existing_key_file_account):
    new_password = "321"
    assert "SUCCESS" in accounts_runner.invoke(
        "change-password",
        EXISTING_KEY_FILE_ALIAS,
        input=f"{PASSWORD}\n{new_password}\n{new_password}",
    )
    assert "SUCCESS" in accounts_runner.invoke(
        "change-password", EXISTING_KEY_FILE_ALIAS, input=f"{new_password}\n{PASSWORD}\n{PASSWORD}"
    )
