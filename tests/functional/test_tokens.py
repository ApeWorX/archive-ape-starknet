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
