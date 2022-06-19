from ape_starknet.utils import is_checksum_address


def test_get_nonce(provider, account, contract):
    initial_nonce = provider.get_nonce(account.contract_address)  # type: ignore

    # Transact to increase nonce
    contract.increase_balance(account.address, 123, sender=account)

    actual = provider.get_nonce(account.contract_address)  # type: ignore
    assert actual == initial_nonce + 1


def test_get_block(provider, contract):
    _ = contract  # Contract fixture used to increase blocks (since deploys happen)
    latest_block_0 = provider.get_block("latest")
    latest_block_1 = provider.get_block(-1)
    latest_block_2 = provider.get_block(latest_block_0.number)
    assert latest_block_0.hash == latest_block_1.hash == latest_block_2.hash


def test_get_transactions_by_block(provider, account, contract):
    # Transact to create data.
    contract.increase_balance(account.address, 123, sender=account)

    transactions = [t for t in provider.get_transactions_by_block("latest")]
    expected_chain_id = provider.chain_id
    expected_abi = [a for a in account.contract_type.mutable_methods if a.name == "__execute__"][0]
    assert len(transactions) == 1
    assert transactions[0].chain_id == expected_chain_id
    assert transactions[0].method_abi == expected_abi
    assert transactions[0].receiver == account.contract_address
    assert is_checksum_address(transactions[0].receiver)
    assert transactions[0].calldata
