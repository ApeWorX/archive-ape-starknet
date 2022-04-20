def test_get_nonce(provider, account, contract):
    initial_nonce = provider.get_nonce(account.contract_address)  # type: ignore

    # Transact to increase nonce
    contract.increase_balance(account.address, 123, sender=account)

    actual = provider.get_nonce(account.contract_address)  # type: ignore
    assert actual == initial_nonce + 1


def test_contract_at(contract, provider):
    actual = provider.contract_at(contract.address)  # type: ignore
    assert actual.address == contract.address
