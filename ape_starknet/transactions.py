from dataclasses import asdict
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from ape.api import ReceiptAPI, TransactionAPI
from ape.exceptions import APINotImplementedError, TransactionError
from ape.types import AddressType, ContractLog
from ape.utils import abstractmethod, cached_property
from ethpm_types import ContractType, HexBytes
from ethpm_types.abi import EventABI, MethodABI
from pydantic import Field, validator
from starknet_py.net.client_models import Call, Deploy, Event, TransactionStatus
from starknet_py.net.models.transaction import Declare, InvokeFunction, Transaction, TransactionType
from starkware.starknet.core.os.contract_address.contract_address import calculate_contract_address
from starkware.starknet.core.os.transaction_hash.transaction_hash import (
    TransactionHashPrefix,
    calculate_declare_transaction_hash,
    calculate_deploy_transaction_hash,
    calculate_transaction_hash_common,
)
from starkware.starknet.public.abi import get_selector_from_name
from starkware.starknet.services.api.contract_class import ContractClass

from ape_starknet.exceptions import ContractTypeNotFoundError
from ape_starknet.utils import (
    EXECUTE_ABI,
    OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE,
    ContractEventABI,
    extract_trace_data,
    to_checksum_address,
    to_int,
)
from ape_starknet.utils.basemodel import StarknetBase


class StarknetTransaction(TransactionAPI, StarknetBase):
    """
    A base transaction class for all Starknet transactions.
    """

    version: int = 1

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

    @property
    def total_transfer_value(self) -> int:
        return self.value + (self.max_fee or 0)


class AccountTransaction(StarknetTransaction):
    """
    Transactions that must go through an account contract.
    (Invoke and Declare).
    """

    max_fee: int = Field(0)
    nonce: Optional[int] = None
    is_prepared: bool = Field(False, exclude=True)

    @validator("max_fee", pre=True, allow_reuse=True)
    def validate_max_fee(cls, value):
        if isinstance(value, str):
            return int(value, 16)

        return value or 0

    @property
    def starknet_signature(self) -> List[int]:
        if self.signature:
            return [to_int(self.signature.r), to_int(self.signature.s)]

        return []


class DeclareTransaction(AccountTransaction):
    sender: AddressType
    type: TransactionType = TransactionType.DECLARE

    @property
    def starknet_contract(self) -> ContractClass:
        return ContractClass.deserialize(self.data)

    @property
    def txn_hash(self) -> HexBytes:
        return calculate_declare_transaction_hash(
            self.starknet_contract,
            self.provider.chain_id,
            self.sender,
        )

    def as_starknet_object(self) -> Declare:
        return Declare(
            contract_class=self.starknet_contract,
            max_fee=self.max_fee,
            nonce=self.nonce,
            sender_address=self.starknet.encode_address(self.sender),
            signature=self.starknet_signature,
            version=self.version,
        )


class DeployTransaction(StarknetTransaction):
    salt: Optional[int] = None  # Only None when unknown, but required when sending

    caller_address: int = 0
    constructor_calldata: Union[List, Tuple] = []
    token: Optional[str] = None
    type: TransactionType = TransactionType.DEPLOY

    """Aliases"""
    data: bytes = Field(alias="contract_code")

    """Ignored"""
    receiver: Optional[AddressType] = Field(None, exclude=True)

    @property
    def starknet_contract(self) -> Optional[ContractClass]:
        return ContractClass.deserialize(self.data)

    @property
    def txn_hash(self) -> HexBytes:
        contract_address = calculate_contract_address(
            contract_class=self.starknet_contract,
            constructor_calldata=self.constructor_calldata,
            deployer_address=self.caller_address,
            salt=self.salt,
        )
        hash_int = calculate_deploy_transaction_hash(
            chain_id=self.provider.chain_id,
            contract_address=contract_address,
            constructor_calldata=self.constructor_calldata,
            version=self.version,
        )
        return HexBytes(hash_int)

    def as_starknet_object(self) -> Deploy:
        return Deploy(
            constructor_calldata=self.constructor_calldata,
            contract_address_salt=self.salt,
            contract_definition=self.starknet_contract,
            version=self.version,
        )


class InvokeFunctionTransaction(AccountTransaction):
    method_abi: MethodABI
    sender: Optional[AddressType] = None
    type: TransactionType = TransactionType.INVOKE_FUNCTION

    """Aliases"""
    data: List[Any] = Field(alias="calldata")  # type: ignore
    receiver: AddressType = Field(alias="contract_address")

    @validator("receiver", pre=True, allow_reuse=True)
    def validate_receiver(cls, value):
        return to_checksum_address(value)

    @validator("max_fee", pre=True, allow_reuse=True)
    def validate_max_fee(cls, value):
        return to_int(value)

    @property
    def receiver_int(self) -> int:
        return self.starknet.encode_address(self.receiver)

    @property
    def contract_type(self) -> ContractType:
        contract_type = self.get_contract_type(self.receiver)
        if not contract_type:
            raise ContractTypeNotFoundError(self.receiver)

        return contract_type

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
            max_fee=self.max_fee or 0,
            tx_hash_prefix=TransactionHashPrefix.INVOKE,
            version=self.version,
        )
        return HexBytes(hash_int)

    def as_starknet_object(self) -> InvokeFunction:
        return InvokeFunction(
            calldata=self.data,
            contract_address=self.receiver_int,
            max_fee=self.max_fee or 0,
            nonce=self.nonce,
            signature=self.starknet_signature,
            version=self.version,
        )

    def _as_call(self) -> InvokeFunction:
        receiver_int = self.starknet.encode_address(self.receiver)
        return Call(to_addr=receiver_int, selector=self.entry_point_selector, calldata=self.data)

    def to_execute_transaction(self) -> "InvokeFunctionTransaction":
        """
        Convert this transaction to an account ``__execute__`` transaction.
        """

        stark_tx = self.as_starknet_object()
        account_call = {
            "to": stark_tx.contract_address,
            "selector": self.entry_point_selector,
            "data_offset": 0,
            "data_len": len(stark_tx.calldata),
        }
        full_abi = OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE.abi
        entire_call_data = [[account_call], stark_tx.calldata]
        self.data = self.starknet.encode_calldata(full_abi, EXECUTE_ABI, entire_call_data)

        if self.sender:
            self.receiver = self.sender

        self.sender = None
        self.method_abi = EXECUTE_ABI
        return self


class StarknetReceipt(ReceiptAPI, StarknetBase):
    """
    An object represented a confirmed transaction in Starknet.
    """

    status: TransactionStatus
    # TODO: Figure out why None sometimes
    block_hash: Optional[str] = None

    """Aliased"""
    txn_hash: str = Field(alias="hash")
    gas_used: int = Field(alias="actual_fee")

    @property
    def return_value(self) -> Any:
        raise APINotImplementedError("'return_value' can only be accessed on InvokeTransactions")

    @validator("block_hash", pre=True, allow_reuse=True)
    def validate_block_hash(cls, value):
        return HexBytes(value).hex() if value else value

    @validator("txn_hash", pre=True, allow_reuse=True)
    def validate_transaction_hash(cls, value):
        if isinstance(value, int):
            return HexBytes(value).hex()

    @property
    def ran_out_of_gas(self) -> bool:
        return False  # Overidden by Invoke receipts

    @property
    def total_fees_paid(self) -> int:
        return 0  # Overidden by Invoke receipts

    def decode_logs(self, abi: Optional[ContractEventABI] = None) -> Iterator[ContractLog]:
        # Overriden in InvocationReceipt
        pass


class DeployReceipt(StarknetReceipt):
    contract_address: AddressType
    status: TransactionStatus

    @validator("contract_address", pre=True, allow_reuse=True)
    def validate_contract_address(cls, value):
        if isinstance(value, int):
            return to_checksum_address(value)

        return value


class InvocationReceipt(StarknetReceipt):
    """Aliased"""

    logs: List[dict] = Field(alias="events")

    @validator("logs", pre=True, allow_reuse=True)
    def validate_logs(cls, value):
        if value and isinstance(value[0], Event):
            value = [asdict(event) for event in value]

        return value

    @property
    def ran_out_of_gas(self) -> bool:
        return self.gas_used >= (self.max_fee or 0)

    @property
    def total_fees_paid(self) -> int:
        return self.gas_used

    @cached_property
    def trace(self) -> Dict:  # type: ignore
        trace = self.provider._get_single_trace(self.block_number, int(self.txn_hash, 16))
        return extract_trace_data(trace) if trace else {}

    @property
    def returndata(self):
        return self.trace.get("result", [])

    @cached_property
    def return_value(self) -> Any:
        return self.starknet.decode_returndata(self.method_abi, self.returndata)

    def decode_logs(
        self,
        abi: Optional[ContractEventABI] = None,
    ) -> Iterator[ContractLog]:

        log_data_items: List[Dict] = []
        for log in self.logs:
            log_data = {
                **log,
                "block_hash": self.block_hash,
                "transaction_hash": self.txn_hash,
                "block_number": self.block_number,
            }
            log_data_items.append(log_data)

        if abi is not None:
            if not isinstance(abi, (list, tuple)):
                abi = [abi]

            event_abis: List[EventABI] = [a.abi if not isinstance(a, EventABI) else a for a in abi]
            yield from self.starknet.decode_logs(log_data_items, *event_abis)

        else:
            # If ABI is not provided, decode all events
            addresses = {self.starknet.decode_address(x["from_address"]) for x in log_data_items}
            contract_types = self.chain_manager.contracts.get_multiple(addresses)
            # address → selector → abi
            selectors = {
                address: {get_selector_from_name(e.name): e for e in contract.events}
                for address, contract in contract_types.items()
            }
            for log in log_data_items:
                contract_address = self.starknet.decode_address(log["from_address"])
                if contract_address not in selectors:
                    continue

                for event_key in log.get("keys", []):
                    event_abi = selectors[contract_address][event_key]
                    yield from self.starknet.decode_logs([log], event_abi)


class ContractDeclaration(StarknetReceipt):
    """
    The result of declaring a contract type in Starknet.
    """

    class_hash: int

    @validator("class_hash", pre=True)
    def validate_class_hash(cls, value):
        if isinstance(value, str):
            return int(value, 16)
        elif isinstance(value, bytes):
            return to_int(value)
        else:
            return value

    @cached_property
    def contract_type(
        self,
    ) -> ContractType:
        contract_type = self.get_local_contract_type(self.class_hash)
        if not contract_type:
            raise TransactionError(message="Contract type declaration was not successful.")

        return contract_type


__all__ = [
    "ContractDeclaration",
    "InvokeFunctionTransaction",
    "StarknetReceipt",
    "StarknetTransaction",
]
