import pytest
from ape.contracts import ContractInstance


@pytest.fixture
def ethereum_account(accounts):
    return accounts.test_accounts[0]


def test_multiple_networks_in_test(provider, networks, project, ethereum_account):
    assert provider.chain_id == 1536727068981429685321

    with networks.ethereum.local.use_provider("test"):
        eth_contract = project.EthContract.deploy(sender=ethereum_account)
        assert isinstance(eth_contract, ContractInstance)
