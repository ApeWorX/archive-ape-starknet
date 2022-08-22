import pytest
from ape.contracts import ContractInstance


@pytest.fixture(scope="module")
def in_ethereum(networks):
    with networks.parse_network_choice("ethereum:local"):
        yield


@pytest.fixture(scope="module")
def in_starknet(networks):
    with networks.parse_network_choice("starknet:local"):
        yield


@pytest.fixture(scope="module")
def eth_contract(in_ethereum, eth_account, eth_contract_container):
    yield eth_account.deploy(eth_contract_container, sender=eth_account)


@pytest.fixture(scope="module")
def stark_contract(in_starknet, contract):
    yield contract


def test_use_eth_network_from_fixture(eth_contract, eth_account):
    # Shows that we can write Ethereum-only tests within a multi-chain test module
    # (NOTE: 'starknet' is the default ecosystem for this project)
    eth_contract.setNumber(123, sender=eth_account)
    assert eth_contract.myNumber() == 123


def test_use_starknet_network_from_fixture(account, stark_contract):
    # Shows that we can write Starknet-only tests within a multi-chain test module
    receipt = stark_contract.increase_balance(account.address, 123, sender=account)
    assert not receipt.failed


def test_switch_to_ethereum_mid_test(
    networks, provider, eth_account, eth_contract_container, contract, account
):
    receipt = contract.increase_balance(account.address, 123, sender=account)
    assert not receipt.failed

    # Shows that we can change to Ethereum within an individual test
    starknet_chain_id = provider.chain_id

    with networks.ethereum.local.use_provider("test") as eth_provider:
        # Verify the chain changed
        assert eth_provider.chain_id != starknet_chain_id

        # Deploy and interact with a contract on Ethereum
        eth_contract = eth_contract_container.deploy(sender=eth_account)
        receipt = eth_contract.setNumber(123, sender=eth_account)
        assert not receipt.failed
        assert isinstance(eth_contract, ContractInstance)
        assert eth_contract.myNumber() == 123

    # Switch back to Starknet
    receipt = contract.increase_balance(account.address, 123, sender=account)
    assert not receipt.failed
