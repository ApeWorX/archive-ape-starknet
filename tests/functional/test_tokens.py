from pathlib import Path

import pytest
from ape.api.networks import LOCAL_NETWORK_NAME

from ape_starknet import tokens as _tokens

all_tokens = pytest.mark.parametrize(
    "token",
    (
        "eth",
        "test_token",
        # "proxy_token",  # TODO: Fix local proxies
    ),
)


@pytest.fixture(scope="module")
def token_contract(config, account, token_initial_supply, project):
    project_path = Path(__file__).parent.parent / "projects" / "token"

    with config.using_project(project_path):
        yield project.get_contract("TestToken").deploy(
            123123, 321321, token_initial_supply, account.address
        )


@pytest.fixture(scope="module")
def proxy_token_contract(config, account, token_initial_supply, token_contract, project):
    project_path = Path(__file__).parent.parent / "projects" / "proxy"

    with config.using_project(project_path):
        contract = project.get_contract("Proxy").deploy(token_contract.address)
        _tokens.add_token("proxy_token", LOCAL_NETWORK_NAME, contract.address)
        return _tokens["proxy_token"]


@pytest.fixture(scope="module")
def tokens(token_contract, proxy_token_contract, provider, account):
    _tokens.add_token("test_token", LOCAL_NETWORK_NAME, token_contract.address)
    return _tokens


@all_tokens
def test_get_balance(tokens, account, token_initial_supply, token):
    if token == "eth":
        # Likely spent fees
        assert tokens.get_balance(account)
    else:
        assert tokens.get_balance(account, token=token) == token_initial_supply


@all_tokens
def test_transfer(tokens, account, second_account, token):
    initial_balance = tokens.get_balance(second_account.address, token=token)
    tokens.transfer(account.address, second_account.address, 10, token=token)
    assert tokens.get_balance(second_account.address, token=token) == initial_balance + 10


def test_large_transfer(tokens, account, second_account):
    initial_balance = tokens.get_balance(second_account.address, token="test_token")

    # Value large enough to properly test Uint256 logic
    balance_to_transfer = 2**128 + 1
    tokens.transfer(
        account.address, second_account.address, balance_to_transfer, token="test_token"
    )
    actual = tokens.get_balance(second_account.address, token="test_token")
    expected = initial_balance + balance_to_transfer
    assert actual == expected


def test_event_log_arguments(token_contract, account, second_account):
    amount0 = 10
    amount1 = 2**128 + 42
    receipt = token_contract.fire_events(second_account.address, amount0, amount1, sender=account)

    transfer_logs = list(receipt.decode_logs(token_contract.Transfer))
    assert len(transfer_logs) == 1
    log = transfer_logs[0]
    assert log.from_ == int(account.address, 16)
    assert log.to == int(second_account.address, 16)
    assert log.value == amount0

    mint_logs = list(receipt.decode_logs(token_contract.Mint))
    assert len(mint_logs) == 1
    log = mint_logs[0]
    assert log.sender == int(account.address, 16)
    assert log.amount0 == amount0
    assert log.amount1 == amount1
    assert log.to == int(second_account.address, 16)
