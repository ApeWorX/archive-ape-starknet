from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from ape.api import ReceiptAPI, TransactionAPI
from ape.contracts import ContractEvent
from ape.types import AddressType, ContractLog
from ape.utils import abstractmethod
from eth_utils import to_bytes, to_int
from ethpm_types import ContractType, HexBytes
from ethpm_types.abi import EventABI, MethodABI
from pydantic import Field
from starknet_py.constants import TxStatus  # type: ignore
from starknet_py.net.models.transaction import (  # type: ignore
    Deploy,
    InvokeFunction,
    Transaction,
    TransactionType,
)
from starkware.starknet.core.os.contract_address.contract_address import (  # type: ignore
    calculate_contract_address,
)
from starkware.starknet.core.os.transaction_hash.transaction_hash import (  # type: ignore
    TransactionHashPrefix,
    calculate_deploy_transaction_hash,
    calculate_transaction_hash_common,
)
from starkware.starknet.public.abi import get_selector_from_name  # type: ignore
from starkware.starknet.services.api.contract_class import ContractClass  # type: ignore

from ape_starknet.utils.basemodel import StarknetMixin


class StarknetTransaction(TransactionAPI):
    """
    A base transaction class for all Starknet transactions.
    """

    status: int = TxStatus.NOT_RECEIVED.value
    version: int = 0

    """Ignored"""
    gas_limit: int = Field(0, exclude=True)
    max_fee: Optional[int] = Field(None, exclude=True)
    max_priority_fee: Optional[int] = Field(None, exclude=True)

    class Config:
        use_enum_values = True

    def serialize_transaction(self) -> dict:  # type: ignore
        return self.dict()

    @abstractmethod
    def as_starknet_object(self) -> Transaction:
        """
        Convert :class:`~ape.api.providers.TransactionAPI` to its Starknet
        transaction equivalent so it can be accepted by the core Starknet OS
        framework.
        """


class DeployTransaction(StarknetTransaction):
    type: TransactionType = TransactionType.DEPLOY
    salt: int
    constructor_calldata: Union[List, Tuple] = []
    caller_address: int = 0
    token: Optional[str] = None

    """Aliases"""
    data: bytes = Field(alias="contract_code")  # type: ignore

    """Ignored"""
    receiver: Optional[str] = Field(None, exclude=True)

    @property
    def starknet_contract(self) -> ContractClass:
        return ContractClass.deserialize(self.data)

    @property
    def txn_hash(self) -> HexBytes:
        contract_address = calculate_contract_address(
            contract_class=self.starknet_contract,
            constructor_calldata=self.constructor_calldata,
            deployer_address=self.caller_address,
            salt=self.salt,
        )
        chain_id = self.provider.chain_id
        hash_int = calculate_deploy_transaction_hash(
            chain_id=chain_id,
            contract_address=contract_address,
            constructor_calldata=self.constructor_calldata,
            version=self.version,
        )
        return HexBytes(to_bytes(hash_int))

    def as_starknet_object(self) -> Deploy:
        contract = ContractClass.deserialize(self.data)
        return Deploy(
            constructor_calldata=self.constructor_calldata,
            contract_address_salt=self.salt,
            contract_definition=contract,
            version=self.version,
        )


class InvokeFunctionTransaction(StarknetTransaction, StarknetMixin):
    type: TransactionType = TransactionType.INVOKE_FUNCTION
    method_abi: MethodABI
    max_fee: int = 0
    sender: Optional[AddressType] = None

    """Aliases"""
    data: List[Any] = Field(alias="calldata")  # type: ignore
    receiver: AddressType = Field(alias="contract_address")

    @property
    def receiver_int(self) -> int:
        return self.starknet.encode_address(self.receiver)

    @property
    def contract_type(self) -> ContractType:
        return self.chain_manager.contracts[self.receiver]

    @property
    def entry_point_selector(self) -> int:
        return get_selector_from_name(self.method_abi.name)

    @property
    def txn_hash(self) -> HexBytes:
        hash_int = calculate_transaction_hash_common(
            additional_data=[],
            calldata=self.data,
            chain_id=self.provider.chain_id,
            contract_address=self.receiver_int,
            entry_point_selector=self.entry_point_selector,
            max_fee=self.max_fee,
            tx_hash_prefix=TransactionHashPrefix.INVOKE,
            version=self.version,
        )
        return HexBytes(to_bytes(hash_int))

    def as_starknet_object(self) -> InvokeFunction:
        return InvokeFunction(
            calldata=self.data,
            contract_address=self.receiver_int,
            entry_point_selector=self.entry_point_selector,
            signature=[to_int(self.signature.r), to_int(self.signature.s)]
            if self.signature
            else [],
            max_fee=self.max_fee,
            version=self.version,
        )


class StarknetReceipt(ReceiptAPI, StarknetMixin):
    """
    An object represented a confirmed transaction in Starknet.
    """

    type: TransactionType
    status: TxStatus
    actual_fee: int
    max_fee: int

    # NOTE: Might be a backend bug causing this to be None
    block_hash: Optional[str] = None  # type: ignore
    block_number: Optional[int] = None  # type: ignore
    return_value: List[int] = []

    """Ignored"""
    sender: str = Field("", exclude=True)
    gas_used: int = Field(0, exclude=True)
    gas_price: int = Field(0, exclude=True)
    gas_limit: int = Field(0, exclude=True)

    """Aliased"""
    txn_hash: str = Field(alias="transaction_hash")
    logs: List[dict] = Field(alias="events")

    @property
    def ran_out_of_gas(self) -> bool:
        return self.max_fee == self.actual_fee

    @property
    def total_fees_paid(self) -> int:
        return self.actual_fee

    def decode_logs(self, abi: Union[EventABI, ContractEvent]) -> Iterator[ContractLog]:
        """
        Decode the logs on the receipt.

        Args:
            abi (``EventABI``): The ABI of the event to decode into logs.

        Returns:
            Iterator[:class:`~ape.types.ContractLog`]
        """
        if not isinstance(abi, EventABI):
            abi = abi.abi

        log_data_items: List[Dict] = []
        for log in self.logs:
            log_data = {
                **log,
                "block_hash": self.block_hash,
                "transaction_hash": self.txn_hash,
                "block_number": self.block_number,
            }
            log_data_items.append(log_data)

        yield from self.starknet.decode_logs(abi, log_data_items)


__all__ = [
    "DeployTransaction",
    "InvokeFunctionTransaction",
    "StarknetReceipt",
    "StarknetTransaction",
]
