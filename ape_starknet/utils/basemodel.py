from functools import cached_property
from typing import TYPE_CHECKING, List, Optional, Union, cast

from ape.types import AddressType
from ape.utils import ManagerAccessMixin
from eth_utils import is_0x_prefixed
from ethpm_types import ContractType
from hexbytes import HexBytes
from starkware.starknet.compiler.compile import compile_starknet_files
from starkware.starknet.core.os.contract_class.deprecated_class_hash import (
    compute_deprecated_class_hash,
)
from starkware.starknet.services.api.contract_class.contract_class import DeprecatedCompiledClass

if TYPE_CHECKING:
    from ape_starknet.accounts import StarknetAccountContainer
    from ape_starknet.config import StarknetConfig
    from ape_starknet.ecosystems import Starknet
    from ape_starknet.explorer import StarknetExplorer
    from ape_starknet.provider import StarknetProvider
    from ape_starknet.tokens import TokenManager
    from ape_starknet.udc import UniversalDeployer


class StarknetBase(ManagerAccessMixin):
    """
    Starknet Base Model
    """

    @property
    def starknet_config(self) -> "StarknetConfig":
        return cast("StarknetConfig", self.config_manager.get_config("starknet"))

    @property
    def starknet(self) -> "Starknet":
        return cast("Starknet", self.network_manager.starknet)

    @property
    def starknet_explorer(self) -> "StarknetExplorer":
        explorer = self.provider.network.explorer
        assert explorer  # For mypy
        return cast("StarknetExplorer", explorer)

    @property
    def provider(self) -> "StarknetProvider":
        return cast("StarknetProvider", super().provider)

    @property
    def account_container(self) -> "StarknetAccountContainer":
        return cast("StarknetAccountContainer", self.account_manager.containers["starknet"])

    @property
    def tokens(self) -> "TokenManager":
        from ape_starknet.tokens import tokens

        return tokens

    @cached_property
    def universal_deployer(self) -> "UniversalDeployer":
        from ape_starknet.udc import UniversalDeployer

        return UniversalDeployer()

    def get_contract_type(self, address: AddressType) -> Optional[ContractType]:
        # Force explorer in Local networks since Ape turns it off by default
        return self.chain_manager.contracts.get(
            address
        ) or self.starknet_explorer.get_contract_type(address)

    def get_local_contract_type(self, class_hash: int) -> Optional[ContractType]:
        """
        Given a class hash, find and return its ``ethpm_types.ContractType``.
        """

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
                contract_class = create_contract_class(code)
            except UnicodeDecodeError:
                continue

            contract_cls = create_contract_class(contract_class)
            computed_class_hash = compute_deprecated_class_hash(contract_cls)
            if computed_class_hash == class_hash:
                return contract_type

        return None


def create_contract_class(code: Union[str, bytes]) -> DeprecatedCompiledClass:
    if isinstance(code, str) and is_0x_prefixed(code):
        return DeprecatedCompiledClass.deserialize(HexBytes(code))

    elif isinstance(code, str):
        return DeprecatedCompiledClass.loads(code)

    elif isinstance(code, bytes):
        return DeprecatedCompiledClass.deserialize(code)

    else:
        raise TypeError(f"Unhandled bytecode type '{code}'.")


def get_contract_class(
    source: Optional[str] = None,
    contract_class: Optional[DeprecatedCompiledClass] = None,
    cairo_path: Optional[List[str]] = None,
    disable_hint_validation: bool = False,
) -> DeprecatedCompiledClass:
    if contract_class is None:
        contract_class = compile_starknet_files(
            files=[source],
            debug_info=True,
            cairo_path=cairo_path,
            disable_hint_validation=disable_hint_validation,
        )
