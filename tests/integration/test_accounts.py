import pytest

from ..conftest import ALIAS, CONTRACT_ADDRESS, EXISTING_KEY_FILE_ALIAS, PASSWORD

NEW_ALIAS = f"{ALIAS}new"


@pytest.fixture
def deployed_account(runner, ape_cli, account_container):
    runner.invoke(ape_cli, ["starknet", "accounts", "create", NEW_ALIAS], catch_exceptions=False)

    yield account_container.load(NEW_ALIAS)

    runner.invoke(ape_cli, ["starknet", "accounts", "delete", NEW_ALIAS], catch_exceptions=False)


def test_create_and_delete(runner, ape_cli):
    """
    Integration test for accounts.
    It all happens under one test because it is really slow to deploy accounts.
    """

    result = runner.invoke(
        ape_cli, ["starknet", "accounts", "create", NEW_ALIAS], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(ape_cli, ["starknet", "accounts", "list"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert NEW_ALIAS in result.output

    result = runner.invoke(
        ape_cli, ["starknet", "accounts", "delete", NEW_ALIAS], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert NEW_ALIAS in result.output
    result = runner.invoke(ape_cli, ["starknet", "accounts", "list"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert NEW_ALIAS not in result.output


def test_delete_single_deployment(runner, ape_cli, existing_key_file_account):
    result = runner.invoke(
        ape_cli,
        [
            "starknet",
            "accounts",
            "delete",
            EXISTING_KEY_FILE_ALIAS,
            "--network",
            "starknet:mainnet",
        ],
        catch_exceptions=False,
        input=f"{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(ape_cli, ["starknet", "accounts", "list"], catch_exceptions=False)

    # The account should still have a remaining deployment and thus still found in output
    assert EXISTING_KEY_FILE_ALIAS in result.output

    # Only the mainnet deployment should have gotten deleted
    output_lines = result.output.split("\n")
    for line in output_lines:
        if line.startswith("Contract address (mainnet)"):
            assert CONTRACT_ADDRESS not in line


def test_list(runner, ape_cli, existing_key_file_account):
    result = runner.invoke(ape_cli, ["starknet", "accounts", "list"], catch_exceptions=False)
    assert EXISTING_KEY_FILE_ALIAS in result.output


def test_change_password(ape_cli, runner, existing_key_file_account):
    new_password = "321"
    result = _change_password(runner, ape_cli, PASSWORD, new_password)
    try:
        assert result.exit_code == 0, result.output
    finally:
        _change_password(runner, ape_cli, new_password, PASSWORD)


def _change_password(runner, ape_cli, old_password: str, new_password: str):
    valid_input = [old_password, new_password, new_password]
    input_str = "\n".join(valid_input) + "\n"
    return runner.invoke(
        ape_cli,
        ["starknet", "accounts", "change-password", EXISTING_KEY_FILE_ALIAS],
        input=input_str,
    )
