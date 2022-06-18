def test_get_nonce(provider, account, contract):
    initial_nonce = provider.get_nonce(account.contract_address)  # type: ignore

    # Transact to increase nonce
    contract.increase_balance(account.address, 123, sender=account)

    actual = provider.get_nonce(account.contract_address)  # type: ignore
    assert actual == initial_nonce + 1


def test_get_transactions_by_block(provider, account, contract):
    # Transact to create data.
    contract.increase_balance(account.address, 123, sender=account)

    transactions = [t for t in provider.get_transactions_by_block("latest")]
    assert len(transactions) == 1
