from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from ape.api import ReceiptAPI, TransactionAPI
from ape.contracts import ContractEvent
from ape.exceptions import ProviderError, TransactionError
from ape.types import AddressType, ContractLog
from ape.utils import abstractmethod
from eth_utils import to_int
from ethpm_types.abi import EventABI, MethodABI
from hexbytes import HexBytes
from pydantic import Field
from starknet_py.constants import TxStatus  # type: ignore
from starknet_py.net.models.transaction import (  # type: ignore
    Deploy,
    InvokeFunction,
    Transaction,
    TransactionType,
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
    constructor_calldata: List[int] = []
    caller_address: int = 0
    token: Optional[str] = None

    """Aliases"""
    data: bytes = Field(alias="contract_code")  # type: ignore

    """Ignored"""
    receiver: Optional[str] = Field(None, exclude=True)

    def as_starknet_object(self) -> Deploy:
        contract = ContractClass.deserialize(self.data)
        return Deploy(
            contract_address_salt=self.salt,
            contract_definition=contract,
            constructor_calldata=self.constructor_calldata,
            version=0,
        )


class InvokeFunctionTransaction(StarknetTransaction, StarknetMixin):
    type: TransactionType = TransactionType.INVOKE_FUNCTION
    method_abi: MethodABI
    max_fee: int = 0
    sender: Optional[AddressType] = None

    """Aliases"""
    data: List[Any] = Field(alias="calldata")  # type: ignore
    receiver: AddressType = Field(alias="contract_address")

    def as_starknet_object(self) -> InvokeFunction:
        if not self.provider.client:
            # **NOTE**: This check is mostly done for mypy.
            raise ProviderError("Must be connected to a Starknet provider.")

        contract_address_int = self.starknet.encode_address(self.receiver)
        contract_type = self.chain_manager.contracts.get(self.receiver)
        if not contract_type:
            raise TransactionError(message=f"Unknown contract '{self.receiver}'.")

        contract_abi = [a.dict() for a in contract_type.abi]
        selector = get_selector_from_name(self.method_abi.name)
        encoded_call_data = self.starknet.encode_calldata(contract_abi, self.method_abi, self.data)

        return InvokeFunction(
            contract_address=contract_address_int,
            entry_point_selector=selector,
            calldata=encoded_call_data,
            signature=[to_int(self.signature.r), to_int(self.signature.s)]
            if self.signature
            else [],
            max_fee=self.max_fee,
            version=self.version,
        )

    def decode_calldata(self) -> List[Union[int, Tuple[int, ...]]]:
        call_data: List[Union[int, Tuple[int, ...]]] = []

        def convert(item: Any) -> int:
            if isinstance(item, HexBytes):
                return int(item.hex(), 16)
            elif isinstance(item, str):
                return int(item, 16)
            elif item is not None:
                return item

            raise ValueError(f"Unable to handle argument type '{type(item)}'.")

        for item in self.data:
            if isinstance(item, (tuple, list)):
                tuple_args = tuple([convert(v) for v in item])
                call_data.append(tuple_args)
            else:
                call_data.append(convert(item))

        return call_data


class StarknetReceipt(ReceiptAPI, StarknetMixin):
    """
    An object represented a confirmed transaction in Starknet.
    """

    type: TransactionType
    status: TxStatus

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
        # Errors elsewhere if we run out of gas.
        return False

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
