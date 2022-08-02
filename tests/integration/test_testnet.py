import pytest

from ape_starknet.exceptions import StarknetProviderError


@pytest.fixture(scope="module")
def testnet_provider(networks):
    with networks.parse_network_choice("starknet:testnet") as provider:
        yield provider


@pytest.fixture(scope="module")
def eth_contract(testnet_provider):
    return testnet_provider.tokens["eth"]


def test_can_connect_to_testnet(eth_contract):
    eth_contract.balanceOf("0x348ef2b95e31269b4a1c019428723e3a33cd964f92ad866741f189b88be3bc0")


def test_is_token(eth_contract, tokens):
    # Ensure it's recognized as a token
    assert tokens.is_token(eth_contract)


def test_revert_message_no_account_found(eth_contract, account):
    # It will obviously fail because we are using a local account
    reason = "No contract found for identifier.*"
    with pytest.raises(StarknetProviderError, match=reason):
        eth_contract.increaseAllowance(account, 1, sender=account)
