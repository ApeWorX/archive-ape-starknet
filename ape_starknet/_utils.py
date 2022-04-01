from ape.api.networks import LOCAL_NETWORK_NAME
from starkware.starknet.definitions.general_config import StarknetChainId  # type: ignore

PLUGIN_NAME = "starknet"
NETWORKS = {
    # chain_id, network_id
    "mainnet": (StarknetChainId.MAINNET.value, StarknetChainId.MAINNET.value),
    "testnet": (StarknetChainId.TESTNET.value, StarknetChainId.TESTNET.value),
}


def get_chain_id(network_name: str) -> int:
    if network_name == LOCAL_NETWORK_NAME:
        return StarknetChainId.TESTNET.value  # Use TESTNET chain ID for local network

    if network_name not in NETWORKS:
        raise ValueError(f"Unknown network '{network_name}'.")

    return NETWORKS[network_name][0]
