def test_get_contract_instance(contract, chain):
    actual = chain.contracts.instance_at(contract.address)
    assert actual.address == contract.address
