from ape.api import PluginConfig
from ape.api.networks import LOCAL_NETWORK_NAME


class NetworkConfig(PluginConfig):
    required_confirmations: int = 0
    block_time: int = 0
    default_provider: str = "starknet"


class ProviderConfig(PluginConfig):
    mainnet: dict = {"uri": "https://alpha-mainnet.starknet.io"}
    testnet: dict = {"uri": "https://alpha4.starknet.io"}
    local: dict = {"uri": "http://127.0.0.1:8545"}


class StarknetConfig(PluginConfig):
    mainnet: NetworkConfig = NetworkConfig(required_confirmations=7, block_time=13)  # type: ignore
    testnet: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=15)  # type: ignore
    local: NetworkConfig = NetworkConfig()  # type: ignore
    default_network: str = LOCAL_NETWORK_NAME
    providers: ProviderConfig = ProviderConfig()
