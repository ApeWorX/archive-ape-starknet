from ape.api import PluginConfig
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.utils import DEFAULT_NUMBER_OF_TEST_ACCOUNTS

from ape_starknet.utils import DEFAULT_ACCOUNT_SEED

DEFAULT_PORT = 8545


class NetworkConfig(PluginConfig):
    required_confirmations: int = 0
    block_time: int = 0
    default_provider: str = "starknet"


class ProviderConfig(PluginConfig):
    mainnet: dict = {"uri": "https://alpha-mainnet.starknet.io"}
    testnet: dict = {"uri": "https://alpha4.starknet.io"}
    local: dict = {
        "uri": f"http://127.0.0.1:{DEFAULT_PORT}",
        "seed": DEFAULT_ACCOUNT_SEED,
        "number_of_accounts": DEFAULT_NUMBER_OF_TEST_ACCOUNTS,
    }


class StarknetConfig(PluginConfig):
    mainnet: NetworkConfig = NetworkConfig(required_confirmations=7, block_time=13)
    testnet: NetworkConfig = NetworkConfig(required_confirmations=2, block_time=15)
    local: NetworkConfig = NetworkConfig()
    default_network: str = LOCAL_NETWORK_NAME
    provider: ProviderConfig = ProviderConfig()
