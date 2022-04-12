from ape import plugins
from ape.api.networks import LOCAL_NETWORK_NAME, NetworkAPI, create_network_type
from ape.types import AddressType

from ape_starknet._utils import NETWORKS, PLUGIN_NAME
from ape_starknet.accounts import StarknetAccountContracts, StarknetKeyfileAccount
from ape_starknet.config import StarknetConfig
from ape_starknet.conversion import StarknetAddressConverter
from ape_starknet.ecosystems import Starknet
from ape_starknet.provider import StarknetProvider
from ape_starknet.tokens import TokenManager

tokens = TokenManager()


@plugins.register(plugins.ConversionPlugin)
def converters():
    yield AddressType, StarknetAddressConverter


@plugins.register(plugins.Config)
def config_class():
    return StarknetConfig


@plugins.register(plugins.EcosystemPlugin)
def ecosystems():
    yield Starknet


@plugins.register(plugins.NetworkPlugin)
def networks():
    for network_name, network_params in NETWORKS.items():
        yield PLUGIN_NAME, network_name, create_network_type(*network_params)

    # NOTE: This works for development providers, as they get chain_id from themselves
    yield PLUGIN_NAME, LOCAL_NETWORK_NAME, NetworkAPI


@plugins.register(plugins.ProviderPlugin)
def providers():
    network_names = [LOCAL_NETWORK_NAME] + [k for k in NETWORKS.keys()]
    for network_name in network_names:
        yield PLUGIN_NAME, network_name, StarknetProvider


@plugins.register(plugins.AccountPlugin)
def account_types():
    return StarknetAccountContracts, StarknetKeyfileAccount
