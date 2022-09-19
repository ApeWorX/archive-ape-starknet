from typing import TYPE_CHECKING, Optional

from ape.api import PluginConfig
from ape.types import AddressType
from ape.utils import ManagerAccessMixin
from ethpm_types import ContractType
from hexbytes import HexBytes
from starknet_py.net.client_models import ContractClass
from starkware.starknet.core.os.class_hash import compute_class_hash
from starkware.starknet.testing.contract_utils import get_contract_class

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

    def get_contract_type(self, address: AddressType) -> Optional[ContractType]:
        # Have to force explorer in Local networks since Ape turns it off by default
        contract_type = self.chain_manager.contracts.get(address)
        if contract_type:
            return contract_type

        return self.starknet_explorer.get_contract_type(address)

    def get_local_contract_type(self, class_hash: int) -> Optional[ContractType]:
        for contract_name, contract_type in self.project_manager.contracts.items():
            if not contract_type.source_id or not contract_type.source_id.endswith(".cairo"):
                continue

            program = contract_type.deployment_bytecode
            if not program:
                continue

            code = program.bytecode
            if not code:
                continue

            try:
                contract_class = ContractClass.deserialize(HexBytes(code))
            except UnicodeDecodeError:
                continue

            contract_cls = get_contract_class(contract_class=contract_class)
            computed_class_hash = compute_class_hash(contract_cls)
            if computed_class_hash == class_hash:
                return contract_type

        return None
