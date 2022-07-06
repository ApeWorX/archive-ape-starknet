def test_can_connect_to_testnet(networks):
    with networks.parse_network_choice("starknet:testnet") as provider:
        eth_contract = provider.tokens["eth"]

        # Make call
        eth_contract.balanceOf("0x348ef2b95e31269b4a1c019428723e3a33cd964f92ad866741f189b88be3bc0")
