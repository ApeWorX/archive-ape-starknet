import pytest
from ape.api.networks import LOCAL_NETWORK_NAME

from .conftest import ApeStarknetCliRunner


@pytest.fixture
def console_runner(ape_cli):
    return ApeStarknetCliRunner(
        ape_cli, ["console", "--network", f"ethereum:{LOCAL_NETWORK_NAME}:test"]
    )


def test_console_accounts_object(ape_cli, console_runner, existing_key_file_account, networks):
    # NOTE: This console connects to Eth-Tester and makes sure we can still _read_
    # starknet accounts.
    output = console_runner.invoke(
        input=f"accounts\naccounts['{existing_key_file_account.alias}']\nexit\n"
    )
    assert existing_key_file_account.contract_address in output, [
        e.name for e in networks.ecosystems
    ]
