from ape.contracts import ContractInstance


def test_multiple_networks_in_test(
    networks, provider, eth_account, eth_contract_container, contract, account
):
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
