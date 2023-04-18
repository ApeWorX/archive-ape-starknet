import json
from functools import cached_property
from typing import TYPE_CHECKING, Dict, Optional, Union, cast

from ape.types import AddressType
from ape.utils import ManagerAccessMixin
from eth_utils import to_text
from ethpm_types import ContractType
from hexbytes import HexBytes
from starknet_py.hash.sierra_class_hash import compute_sierra_class_hash
from starknet_py.net.client_models import (
    CasmClass,
    CasmClassEntryPoint,
    CasmClassEntryPointsByType,
    SierraContractClass,
    SierraEntryPoint,
    SierraEntryPointsByType,
)

if TYPE_CHECKING:
    from ape_starknet.accounts import StarknetAccountContainer
    from ape_starknet.config import StarknetConfig
    from ape_starknet.deployer import UniversalDeployer
    from ape_starknet.ecosystems import Starknet
    from ape_starknet.explorer import StarknetExplorer
    from ape_starknet.provider import StarknetProvider
    from ape_starknet.tokens import TokenManager


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
        from ape_starknet.deployer import UniversalDeployer

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
                sierra_cls = create_sierra_class(code)
            except UnicodeDecodeError:
                continue

            computed_class_hash = compute_sierra_class_hash(sierra_cls)
            if computed_class_hash == class_hash:
                return contract_type

        return None


def create_sierra_class(code: Union[str, bytes, int]) -> SierraContractClass:
    contract_data = json.loads(to_text(HexBytes(code)))
    ep_data = contract_data["entry_points_by_type"]
    entry_points = SierraEntryPointsByType(
        external=[create_sierra_entry_point(v) for v in ep_data["EXTERNAL"]],
        constructor=[create_sierra_entry_point(v) for v in ep_data["CONSTRUCTOR"]],
        l1_handler=[create_sierra_entry_point(v) for v in ep_data["L1_HANDLER"]],
    )
    return SierraContractClass(
        abi=json.dumps(contract_data["abi"]),
        contract_class_version=contract_data["contract_class_version"],
        entry_points_by_type=entry_points,
        sierra_program=contract_data["sierra_program"],
    )


def create_casm_class(code: Union[str, bytes, int]) -> CasmClass:
    class_data = json.loads(to_text(HexBytes(code)))
    ep_data = class_data["entry_points_by_type"]
    entry_points = CasmClassEntryPointsByType(
        external=[create_casm_entry_point(v) for v in ep_data["EXTERNAL"]],
        constructor=[create_casm_entry_point(v) for v in ep_data["CONSTRUCTOR"]],
        l1_handler=[create_casm_entry_point(v) for v in ep_data["L1_HANDLER"]],
    )
    return CasmClass(
        prime=int(class_data["prime"], 16),
        bytecode=[int(x, 16) for x in class_data["bytecode"]],
        hints=class_data["hints"],
        pythonic_hints=class_data.get("pythonic_hints") or [],
        entry_points_by_type=entry_points,
        compiler_version=class_data["compiler_version"],
    )


def create_sierra_entry_point(data: Dict) -> SierraEntryPoint:
    return SierraEntryPoint(function_idx=data["function_idx"], selector=int(data["selector"], 16))


def create_casm_entry_point(data: Dict) -> CasmClassEntryPoint:
    return CasmClassEntryPoint(
        selector=int(data["selector"], 16), offset=data["offset"], builtins=data["builtins"]
    )
