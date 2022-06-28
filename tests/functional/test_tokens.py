from pathlib import Path

import pytest
from ape.api.networks import LOCAL_NETWORK_NAME

from ape_starknet import tokens as _tokens


@pytest.fixture(scope="module")
def token_contract(config, account, token_initial_supply, project):
    project_path = Path(__file__).parent.parent / "projects" / "token"

    with config.using_project(project_path):
        yield project.TestToken.deploy(123123, 321321, token_initial_supply, account.address)


@pytest.fixture(scope="module")
def proxy_token_contract(config, account, token_initial_supply, token_contract, project):
    project_path = Path(__file__).parent.parent / "projects" / "proxy"

    with config.using_project(project_path):
        return project.Proxy.deploy(token_contract.address)


@pytest.fixture
def tokens(token_contract, proxy_token_contract, provider, account):
    _tokens.TOKEN_ADDRESS_MAP["test_token"][LOCAL_NETWORK_NAME] = token_contract.address
    _tokens.TOKEN_ADDRESS_MAP["proxy_token"] = {}
    _tokens.TOKEN_ADDRESS_MAP["proxy_token"][LOCAL_NETWORK_NAME] = token_contract.address
    return _tokens


@pytest.mark.parametrize("token", ("test_token", "proxy_token"))
def test_get_balance(tokens, account, token_initial_supply, token):
    assert tokens.get_balance(account.address, token=token) == token_initial_supply


@pytest.mark.parametrize("token", ("test_token", "proxy_token"))
def test_transfer(tokens, account, second_account, token):
    initial_balance = tokens.get_balance(second_account.address, token=token)
    tokens.transfer(account.address, second_account.address, 10, token=token)
    assert tokens.get_balance(second_account.address, token=token) == initial_balance + 10
