import pytest

from ..conftest import ALIAS, EXISTING_KEY_FILE_ALIAS, PASSWORD

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

    result = runner.invoke(
        ape_cli, ["starknet", "accounts", "delete", NEW_ALIAS], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert NEW_ALIAS in result.output


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
