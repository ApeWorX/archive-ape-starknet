from ..conftest import ALIAS, EXISTING_KEY_FILE_ALIAS

NEW_ALIAS = f"{ALIAS}new"


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
