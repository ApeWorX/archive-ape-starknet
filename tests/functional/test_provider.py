def test_contract_at(contract, provider):
    actual = provider.contract_at(contract.address)
    assert actual.address == contract.address
