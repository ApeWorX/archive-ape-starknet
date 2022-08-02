import pytest
from ape.api.networks import LOCAL_NETWORK_NAME

from .conftest import ApeStarknetCliRunner


@pytest.fixture(scope="session")
def console_runner(ape_cli):
    return ApeStarknetCliRunner(
        ape_cli, ["console", "--network", f"ethereum:{LOCAL_NETWORK_NAME}:test"]
    )


def test_console_accounts_object(ape_cli, console_runner, key_file_account, networks):
    # NOTE: This console connects to Eth-Tester and makes sure we can still _read_
    # starknet accounts.
    output = console_runner.invoke(
        input=["accounts", f"accounts['{key_file_account.alias}']", "exit"]
    )
    assert key_file_account.address in output, [e.name for e in networks.ecosystems]
