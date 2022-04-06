import pytest

from ..conftest import ALIAS, CONTRACT_ADDRESS, EXISTING_KEY_FILE_ALIAS, PASSWORD

NEW_ALIAS = f"{ALIAS}new"


@pytest.fixture
def deployed_account(account_container):
    account_container.deploy_account(NEW_ALIAS)
    yield account_container.load(NEW_ALIAS)
    account_container.delete_account(NEW_ALIAS)


def test_create(runner):
    """
    Integration test for accounts.
    It all happens under one test because it is really slow to deploy accounts.
    """

    output = runner.invoke("create", NEW_ALIAS)
    assert "Account successfully deployed to" in output
    output = runner.invoke("list")
    assert NEW_ALIAS in output

    # Delete newly created account (clean-up)
    runner.invoke("delete", NEW_ALIAS)


def test_delete(runner, existing_key_file_account):
    """
    This integration test deletes a single deployment of an account and then
    re-import it. The account never completely goes away because it is deployed on
    multiple networks.
    """
    output = runner.invoke(
        "delete",
        EXISTING_KEY_FILE_ALIAS,
        "--network",
        "starknet:testnet",
        input=f"{PASSWORD}\n",
    )
    assert EXISTING_KEY_FILE_ALIAS in output
    output = runner.invoke("list")

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
    runner.invoke(
        "import",
        EXISTING_KEY_FILE_ALIAS,
        "--network",
        "starknet:testnet",
        "--address",
        CONTRACT_ADDRESS,
        input=f"{PASSWORD}\n",
    )


def test_import(runner, existing_key_file_account, account_container):
    network = "starknet:testnet"  # NOTE: Does not actually connect
    account_path = account_container.data_folder / "starknet" / f"{NEW_ALIAS}.json"

    if account_path.is_file():
        # Corrupted from previous test
        account_path.unlink()

    private_key = str(CONTRACT_ADDRESS)
    valid_input = f"{private_key}\n{PASSWORD}\n{PASSWORD}"
    runner.invoke(
        "import",
        NEW_ALIAS,
        "--network",
        network,
        "--address",
        CONTRACT_ADDRESS,
        input=valid_input,
    )

    # Clean-up
    runner.invoke(
        "delete",
        NEW_ALIAS,
        "--network",
        network,
        input=f"{PASSWORD}\ny\n",
    )


def test_list(runner, existing_key_file_account):
    assert EXISTING_KEY_FILE_ALIAS in runner.invoke("list")


def test_change_password(runner, existing_key_file_account):
    new_password = "321"
    assert "SUCCESS" in runner.invoke(
        "change-password",
        EXISTING_KEY_FILE_ALIAS,
        input=f"{PASSWORD}\n{new_password}\n{new_password}",
    )
    assert "SUCCESS" in runner.invoke(
        "change-password", EXISTING_KEY_FILE_ALIAS, input=f"{new_password}\n{PASSWORD}\n{PASSWORD}"
    )
