import pytest
from ape.api.networks import LOCAL_NETWORK_NAME

from ape_starknet import tokens as _tokens
from tests.conftest import TOKEN_INITIAL_SUPPLY


@pytest.fixture
def tokens(token_contract, provider, account):
    _tokens.TOKEN_ADDRESS_MAP["test_token"][LOCAL_NETWORK_NAME] = token_contract.address
    return _tokens


def test_get_balance(tokens, account):
    assert tokens.get_balance(account.contract_address, token="test_token") == TOKEN_INITIAL_SUPPLY


def test_transfer(tokens, account, second_account):
    assert tokens.get_balance(second_account.contract_address, token="test_token") == 0
    tokens.transfer(
        account.contract_address, second_account.contract_address, 10, token="test_token"
    )
    assert tokens.get_balance(second_account.contract_address, token="test_token") == 10
