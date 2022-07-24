import pytest

all_tokens = pytest.mark.parametrize(
    "token",
    (
        "eth",
        "test_token",
        # "proxy_token",  # TODO: Fix local proxies
    ),
)


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
