from typing import Any, Dict, List, Optional, cast

from ape.types import AddressType
from ape.utils import cached_property
from ethpm_types import ContractType
from ethpm_types.abi import MethodABI
from starkware.starknet.definitions.fields import ContractAddressSalt

from ape_starknet.transactions import InvokeFunctionTransaction
from ape_starknet.utils.basemodel import StarknetBase

DEFAULT_UDC_ADDRESS: AddressType = cast(
    AddressType, "0x041A78e741e5aF2fec34B695679bc6891742439F7Afb8484ecd7766661aD02bF"
)
DEFAULT_UDC_ABI: List[Dict] = [
    {
        "type": "event",
        "name": "ContractDeployed",
        "inputs": [
            {"name": "address", "type": "felt", "indexed": False},
            {"name": "deployer", "type": "felt", "indexed": False},
            {"name": "unique", "type": "felt", "indexed": False},
            {"name": "classHash", "type": "felt", "indexed": False},
            {"name": "calldata_len", "type": "felt", "indexed": False},
            {"name": "calldata", "type": "felt*", "indexed": False},
            {"name": "salt", "type": "felt", "indexed": False},
        ],
        "anonymous": False,
    },
    {
        "type": "function",
        "name": "deployContract",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "classHash", "type": "felt"},
            {"name": "salt", "type": "felt"},
            {"name": "unique", "type": "felt"},
            {"name": "calldata_len", "type": "felt"},
            {"name": "calldata", "type": "felt*"},
        ],
        "outputs": [{"name": "address", "type": "felt"}],
    },
]


class UniversalDeployer(StarknetBase):
    @cached_property
    def contract_type(self) -> ContractType:
        return ContractType(
            contractName="openzeppelin.utils.presets.UniversalDeployer",
            sourceId="openzeppelin/utils/presets/UniversalDeployer.cairo",
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
    ) -> InvokeFunctionTransaction:
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
        return cast(InvokeFunctionTransaction, txn)

    def _cache_self(self):
        self.chain_manager.contracts[self.address] = self.contract_type
