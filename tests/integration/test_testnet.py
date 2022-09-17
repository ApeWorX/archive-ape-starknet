import pytest


@pytest.fixture(scope="module")
def testnet_provider(networks):
    with networks.parse_network_choice("starknet:testnet") as provider:
        yield provider


@pytest.fixture(scope="module")
def eth_contract(testnet_provider):
    return testnet_provider.tokens["eth"]


def test_can_connect_to_testnet(eth_contract):
    address = "0x348ef2b95e31269b4a1c019428723e3a33cd964f92ad866741f189b88be3bc0"
    assert eth_contract.balanceOf(address) is not None
