import pytest
from ape.exceptions import ContractLogicError


@pytest.fixture(scope="module")
def eth_contract(networks):
    with networks.parse_network_choice("starknet:testnet") as provider:
        yield provider.tokens["eth"]


def test_can_connect_to_testnet(eth_contract):
    eth_contract.balanceOf("0x348ef2b95e31269b4a1c019428723e3a33cd964f92ad866741f189b88be3bc0")


def test_is_token(eth_contract, tokens):
    # Ensure it's recognized as a token
    assert tokens.is_token(eth_contract)


def test_revert_message_no_account_found(eth_contract, account):
    # It will obviously fail because we are using a local account
    with pytest.raises(ContractLogicError) as err:
        eth_contract.increaseAllowance(account, 1, sender=account)

    assert str(err.value) == "No contract found with following identifier {}"
