import pytest
from ape.contracts import ContractContainer, ContractInstance


@pytest.fixture
def in_ethereum(use_local_ethereum):
    with use_local_ethereum:
        yield


@pytest.fixture
def in_starknet(use_local_starknet):
    with use_local_starknet:
        yield


@pytest.fixture(scope="module")
def eth_contract_container(eth_contract_type):
    return ContractContainer(eth_contract_type)


@pytest.fixture(scope="module", autouse=True)
def deploy_eth_contract(use_local_ethereum, eth_account, eth_contract_container):
    with use_local_ethereum:
        return eth_account.deploy(eth_contract_container, sender=eth_account)


@pytest.fixture
def eth_contract(in_ethereum, eth_contract_container):
    return eth_contract_container.deployments[-1]


@pytest.fixture(scope="module")
def stark_contract(use_local_starknet, config, project_path):
    with use_local_starknet:
        with config.using_project(project_path) as project:
            yield project.MyContract.deployments[-1]


def test_use_eth_network_from_fixture(eth_contract, eth_account, in_ethereum):
    # Shows that we can write Ethereum-only tests within a multi-chain test module
    # (NOTE: 'starknet' is the default ecosystem for this project)
    eth_contract.setNumber(123, sender=eth_account)
    assert eth_contract.myNumber() == 123


def test_use_starknet_network_from_fixture(account, stark_contract, in_starknet):
    # Shows that we can write Starknet-only tests within a multi-chain test module
    receipt = stark_contract.increase_balance(account.address, 123, sender=account)
    assert not receipt.failed


def test_switch_to_ethereum_mid_test(
    provider,
    eth_account,
    eth_contract_container,
    stark_contract,
    account,
    in_starknet,
    use_local_ethereum,
):
    receipt = stark_contract.increase_balance(account.address, 123, sender=account)
    assert not receipt.failed

    # Shows that we can change to Ethereum within an individual test
    starknet_chain_id = provider.chain_id

    with use_local_ethereum as eth_provider:
        # Verify the chain changed
        assert eth_provider.chain_id != starknet_chain_id

        # Deploy and interact with a contract on Ethereum
        eth_contract = eth_contract_container.deploy(sender=eth_account)
        receipt = eth_contract.setNumber(123, sender=eth_account)
        assert not receipt.failed
        assert isinstance(eth_contract, ContractInstance)
        assert eth_contract.myNumber() == 123

    # Switch back to Starknet
    receipt = stark_contract.increase_balance(account.address, 123, sender=account)
    assert not receipt.failed
