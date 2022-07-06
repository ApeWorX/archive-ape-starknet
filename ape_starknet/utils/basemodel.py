from typing import TYPE_CHECKING

from ape.api import PluginConfig
from ape.utils import ManagerAccessMixin

if TYPE_CHECKING:
    from ape_starknet.accounts import StarknetAccountContracts
    from ape_starknet.ecosystems import Starknet
    from ape_starknet.explorer import StarknetExplorer
    from ape_starknet.provider import StarknetProvider
    from ape_starknet.tokens import TokenManager


class StarknetBase(ManagerAccessMixin):
    @property
    def starknet_config(self) -> PluginConfig:
        return self.config_manager.get_config("starknet")

    @property
    def starknet(self) -> "Starknet":
        return self.network_manager.starknet  # type: ignore

    @property
    def starknet_explorer(self) -> "StarknetExplorer":
        explorer = self.provider.network.explorer
        assert explorer  # For mypy
        return explorer  # type: ignore

    @property
    def provider(self) -> "StarknetProvider":
        return super().provider  # type: ignore

    @property
    def account_contracts(self) -> "StarknetAccountContracts":
        return self.account_manager.containers["starknet"]  # type: ignore

    @property
    def tokens(self) -> "TokenManager":
        from ape_starknet import tokens

        return tokens
