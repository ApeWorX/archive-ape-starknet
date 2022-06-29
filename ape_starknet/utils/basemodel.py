from typing import TYPE_CHECKING

from ape.api import PluginConfig
from ape.utils import ManagerAccessMixin

if TYPE_CHECKING:
    from ape_starknet.accounts import StarknetAccountContracts
    from ape_starknet.ecosystems import Starknet
    from ape_starknet.provider import StarknetProvider


class StarknetBase(ManagerAccessMixin):
    @property
    def starknet_config(self) -> PluginConfig:
        return self.config_manager.get_config("starknet")

    @property
    def starknet(self) -> "Starknet":
        return self.network_manager.starknet  # type: ignore

    @property
    def provider(self) -> "StarknetProvider":
        return super().provider  # type: ignore

    @property
    def account_contracts(self) -> "StarknetAccountContracts":
        return self.account_manager.containers["starknet"]  # type: ignore
