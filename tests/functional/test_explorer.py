from ape_starknet.accounts import OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE


def test_get_contract_type_tokens(tokens, explorer):
    actual = explorer.get_contract_type(tokens.token_address_map["eth"]["local"])
    expected = tokens.contract_type
    assert actual == expected


def test_get_contract_type_accounts(account, second_account, explorer):
    actual_0 = explorer.get_contract_type(account.address)
    actual_1 = explorer.get_contract_type(second_account.address)
    assert actual_0 == OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE
    assert actual_1 == OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE


def test_get_contract_type_after_deploy(contract, explorer):
    actual = explorer.get_contract_type(contract.address)
    expected = contract.contract_type
    assert actual.abi == expected.abi
