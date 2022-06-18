import pytest
from ape.api.networks import LOCAL_NETWORK_NAME

from ape_starknet import tokens as _tokens


@pytest.fixture
def tokens(token_contract, proxy_token_contract, provider, account):
    _tokens.TOKEN_ADDRESS_MAP["test_token"][LOCAL_NETWORK_NAME] = token_contract.address

    _tokens.TOKEN_ADDRESS_MAP["proxy_token"] = {}
    _tokens.TOKEN_ADDRESS_MAP["proxy_token"][LOCAL_NETWORK_NAME] = token_contract.address

    return _tokens


@pytest.mark.parametrize("token", ("test_token", "proxy_token"))
def test_get_balance(tokens, account, token_initial_supply, token):
    assert tokens.get_balance(account.contract_address, token=token) == token_initial_supply


@pytest.mark.parametrize("token", ("test_token", "proxy_token"))
def test_transfer(tokens, account, second_account, token):
    initial_balance = tokens.get_balance(second_account.contract_address, token=token)
    tokens.transfer(account.contract_address, second_account.contract_address, 10, token=token)
    assert tokens.get_balance(second_account.contract_address, token=token) == initial_balance + 10
