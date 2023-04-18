from typing import Any, Dict, List, Optional, cast

from ape.types import AddressType
from ape.utils import cached_property
from ethpm_types import ContractType
from ethpm_types.abi import MethodABI
from starknet_py.constants import DEFAULT_DEPLOYER_ADDRESS
from starkware.starknet.definitions.fields import ContractAddressSalt

from ape_starknet.transactions import InvokeTransaction
from ape_starknet.utils.basemodel import StarknetBase

DEFAULT_UDC_ADDRESS: AddressType = cast(AddressType, DEFAULT_DEPLOYER_ADDRESS)

# TODO: Replace with actual OpenZeppelin ABI once exists.
#  This was made from a custom implementation of the UDC.
DEFAULT_UDC_ABI: List[Dict] = [
    {
        "inputs": [
            {"name": "classHash", "type": "core::starknet::class_hash::ClassHash"},
            {"name": "salt", "type": "core::felt252"},
            {"name": "unique", "type": "core::bool"},
            {"name": "calldata", "type": "core::array::Array::<core::felt252>"},
        ],
        "name": "deployContract",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": False,
                "name": "address",
                "type": "core::starknet::contract_address::ContractAddress",
            },
            {
                "indexed": False,
                "name": "deployer",
                "type": "core::starknet::contract_address::ContractAddress",
            },
            {"indexed": False, "name": "unique", "type": "core::bool"},
            {
                "indexed": False,
                "name": "classHash",
                "type": "core::starknet::class_hash::ClassHash",
            },
            {"indexed": False, "name": "calldata", "type": "core::array::Array::<core::felt252>"},
            {"indexed": False, "name": "salt", "type": "core::felt252"},
        ],
        "name": "ContractDeployed",
        "type": "event",
    },
]


class UniversalDeployer(StarknetBase):
    @cached_property
    def contract_type(self) -> ContractType:
        return ContractType(
            contractName="UniversalDeployer",
            sourceId="UniversalDeployer.cairo",
            abi=self.abi,
            # NOTE: code is not necessary for its use-cases (use like an interface)
            deploymentBytecode={},
            runtimeBytecode={},
        )

    def __init__(
        self, address: AddressType = DEFAULT_UDC_ADDRESS, abi: Optional[List[Dict]] = None
    ):
        self.address = address
        self.abi = abi or DEFAULT_UDC_ABI
        self._cache_self()
        super().__init__()

    @cached_property
    def deploy_function(self) -> MethodABI:
        method = self.contract_type.mutable_methods["deployContract"]
        method.contract_type = self.contract_type
        return method

    def create_deploy(
        self,
        class_hash: int,
        constructor_arguments: List[Any],
        salt: Optional[int] = None,
        unique: bool = True,
        **kwargs,
    ) -> InvokeTransaction:
        """
        Deploy a contract using the Starknet public Universal Deployer Contract.
        """
        salt = salt or ContractAddressSalt.get_random_value()
        txn = self.starknet.encode_transaction(
            self.address,
            self.deploy_function,
            class_hash,
            salt,
            unique,
            len(constructor_arguments),
            constructor_arguments,
            **kwargs,
        )
        return cast(InvokeTransaction, txn)

    def _cache_self(self):
        self.chain_manager.contracts[self.address] = self.contract_type
