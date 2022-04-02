from typing import List, Optional

from ape.api import ReceiptAPI, TransactionAPI
from ape.types import AddressType
from ape.utils import abstractmethod
from pydantic import Field
from starknet_py.constants import TxStatus  # type: ignore
from starknet_py.net.models.transaction import (  # type: ignore
    Deploy,
    InvokeFunction,
    Transaction,
    TransactionType,
)
from starkware.starknet.services.api.contract_definition import ContractDefinition  # type: ignore


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

    """Aliases"""
    data: bytes = Field(alias="contract_code")  # type: ignore

    """Ignored"""
    receiver: Optional[str] = Field(None, exclude=True)

    def as_starknet_object(self) -> Deploy:
        definition = ContractDefinition.deserialize(self.data)
        return Deploy(
            contract_address_salt=self.salt,
            contract_definition=definition,
            constructor_calldata=self.constructor_calldata,
        )


class InvokeFunctionTransaction(StarknetTransaction):
    type: TransactionType = TransactionType.INVOKE_FUNCTION
    entry_point_selector: int
    max_fee: int = 0

    """Aliases"""
    data: List[int] = Field(alias="calldata")  # type: ignore
    receiver: AddressType = Field(alias="contract_address")

    """Ignored"""
    sender: AddressType = Field("", exclude=True)

    def as_starknet_object(self) -> InvokeFunction:
        contract_address = self.provider.network.ecosystem.encode_address(self.receiver)
        return InvokeFunction(
            contract_address=contract_address,
            entry_point_selector=self.entry_point_selector,
            calldata=self.data,
            signature=[*self.signature] if self.signature else [],
            max_fee=self.max_fee,
            version=self.version,
        )


class StarknetReceipt(ReceiptAPI):
    """
    An object represented a confirmed transaction in Starknet.
    """

    type: TransactionType
    status: TxStatus

    """Ignored"""
    sender: str = Field("", exclude=True)
    gas_used: int = Field(0, exclude=True)
    gas_price: int = Field(0, exclude=True)
    gas_limit: int = Field(0, exclude=True)

    """Aliased"""
    txn_hash: str = Field(alias="transaction_hash")

    @property
    def ran_out_of_gas(self) -> bool:
        # TODO: Handle fees
        return False


__all__ = [
    "DeployTransaction",
    "InvokeFunctionTransaction",
    "StarknetReceipt",
    "StarknetTransaction",
]
