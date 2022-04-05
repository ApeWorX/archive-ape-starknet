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


def test_delete_and_re_import(runner, ape_cli, existing_key_file_account):
    """
    This integration test deletes a single deployment of an account and then
    re-import it. The account never completely goes away because it is deployed on
    multiple networks.
    """
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

    # Re-import the deployment
    result = runner.invoke(
        ape_cli,
        [
            "starknet",
            "accounts",
            "import",
            EXISTING_KEY_FILE_ALIAS,
            "--network",
            "starknet:mainnet",
            "--address",
            CONTRACT_ADDRESS,
        ],
        catch_exceptions=False,
        input=f"{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(ape_cli, ["starknet", "accounts", "list"], catch_exceptions=False)

    # Verify our mainnet deployment has returned
    output_lines = result.output.split("\n")
    did_find = False
    for line in output_lines:
        if CONTRACT_ADDRESS in line:
            if "Contract address (mainnet)" in line:
                did_find = True
                break

    assert did_find, f"Did not find deployment ... {result.output}"


def test_import_new_account(runner, ape_cli, existing_key_file_account):
    private_key = str(CONTRACT_ADDRESS)
    valid_input = f"{private_key}\n{PASSWORD}\n{PASSWORD}"
    result = runner.invoke(
        ape_cli,
        [
            "starknet",
            "accounts",
            "import",
            "__BRAND_NEW_ALIAS__",
            "--network",
            "starknet:testnet",
            "--address",
            CONTRACT_ADDRESS,
        ],
        catch_exceptions=False,
        input=valid_input,
    )
    assert result.exit_code == 0
    runner.invoke(
        ape_cli,
        [
            "starknet",
            "accounts",
            "delete",
            "__BRAND_NEW_ALIAS__",
            "--network",
            "starknet:testnet",
        ],
        catch_exceptions=False,
        input=f"{PASSWORD}\n",
    )


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
