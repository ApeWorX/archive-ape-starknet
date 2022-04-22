import pytest

from .conftest import ApeStarknetCliRunner


@pytest.fixture
def console_runner(ape_cli):
    return ApeStarknetCliRunner(ape_cli, ["console"])


def test_console_accounts_object(ape_cli, console_runner, existing_key_file_account):
    # NOTE: This console connects to Eth-Tester and makes sure we can still _read_
    # starknet accounts.
    output = console_runner.invoke(
        input=f"accounts\naccounts['{existing_key_file_account.alias}']\nexit\n"
    )
    assert existing_key_file_account.contract_address in output
