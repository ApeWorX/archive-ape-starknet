from dataclasses import asdict
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from ape.api import ReceiptAPI, TransactionAPI
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import TransactionError
from ape.types import AddressType, ContractLog
from ape.utils import abstractmethod, cached_property
from eth_utils import to_int
from ethpm_types import ContractType, HexBytes
from ethpm_types.abi import EventABI, MethodABI
from pydantic import Field, validator
from starknet_py.net.client_models import Event, TransactionStatus
from starknet_py.net.models.transaction import (
    Declare,
    Deploy,
    InvokeFunction,
    Transaction,
    TransactionType,
)
from starkware.starknet.core.os.class_hash import compute_class_hash
from starkware.starknet.core.os.contract_address.contract_address import calculate_contract_address
from starkware.starknet.core.os.transaction_hash.transaction_hash import (
    TransactionHashPrefix,
    calculate_declare_transaction_hash,
    calculate_deploy_transaction_hash,
    calculate_transaction_hash_common,
)
from starkware.starknet.public.abi import get_selector_from_name
from starkware.starknet.services.api.contract_class import ContractClass
from starkware.starknet.services.api.gateway.transaction import DECLARE_SENDER_ADDRESS
from starkware.starknet.testing.contract_utils import get_contract_class

from ape_starknet.utils import ContractEventABI, to_checksum_address
from ape_starknet.utils.basemodel import StarknetBase


class StarknetTransaction(TransactionAPI, StarknetBase):
    """
    A base transaction class for all Starknet transactions.
    """

    status: int = TransactionStatus.NOT_RECEIVED
    version: int = 0

    """Ignored"""
    gas_limit: int = Field(0, exclude=True)
    max_fee: Optional[int] = Field(None, exclude=True)
    max_priority_fee: Optional[int] = Field(None, exclude=True)

    class Config:
        use_enum_values = True

    def serialize_transaction(self) -> dict:  # type: ignore
        return self.dict()

    @validator("status", pre=True, allow_reuse=True)
    def validate_status(cls, value):
        if isinstance(value, TransactionStatus):
            return value.value

        elif isinstance(value, str):
            return int(value, 16)

        return value

    @abstractmethod
    def as_starknet_object(self) -> Transaction:
        """
        Convert :class:`~ape.api.providers.TransactionAPI` to its Starknet
        transaction equivalent so it can be accepted by the core Starknet OS
        framework.
        """

    @property
    def total_transfer_value(self) -> int:
        max_fee = self.max_fee or 0
        return self.value + max_fee


class DeclareTransaction(StarknetTransaction):
    sender: AddressType = to_checksum_address(DECLARE_SENDER_ADDRESS)
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
        sender_int = self.starknet.encode_address(self.sender)

        # NOTE: The sender address is a special address, nonce has to be 0, and signatures
        # and fees are not supported.
        return Declare(
            contract_class=self.starknet_contract,
            max_fee=0,
            nonce=0,
            sender_address=sender_int,
            signature=[],
            version=self.version,
        )


class DeployTransaction(StarknetTransaction):
    salt: int

    caller_address: int = 0
    constructor_calldata: Union[List, Tuple] = []
    token: Optional[str] = None
    type: TransactionType = TransactionType.DEPLOY

    """Aliases"""
    data: bytes = Field(alias="contract_code")

    """Ignored"""
    receiver: Optional[str] = Field(None, exclude=True)

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


class InvokeFunctionTransaction(StarknetTransaction):
    max_fee: Optional[int] = None
    method_abi: MethodABI

    sender: Optional[AddressType] = None
    type: TransactionType = TransactionType.INVOKE_FUNCTION

    original_method_abi: Optional[MethodABI] = None
    """
    Only set when invoked from an account `__execute__`
    special method to help decoding return data
    """

    """Aliases"""
    data: List[Any] = Field(alias="calldata")  # type: ignore
    receiver: AddressType = Field(alias="contract_address")

    @validator("receiver", pre=True, allow_reuse=True)
    def validate_receiver(cls, value):
        if isinstance(value, int):
            return to_checksum_address(value)

        return value

    @validator("max_fee", pre=True, allow_reuse=True)
    def validate_max_fee(cls, value):
        if isinstance(value, str):
            return int(value, 16)

        return value

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
            max_fee=self.max_fee or 0,
            tx_hash_prefix=TransactionHashPrefix.INVOKE,
            version=self.version,
        )
        return HexBytes(hash_int)

    def as_starknet_object(self) -> InvokeFunction:
        return InvokeFunction(
            calldata=self.data,
            contract_address=self.receiver_int,
            entry_point_selector=self.entry_point_selector,
            signature=[to_int(self.signature.r), to_int(self.signature.s)]
            if self.signature
            else [],
            max_fee=self.max_fee or 0,
            version=self.version,
        )


class StarknetReceipt(ReceiptAPI, StarknetBase):
    """
    An object represented a confirmed transaction in Starknet.
    """

    status: TransactionStatus
    type: TransactionType

    # NOTE: Might be a backend bug causing this to be None
    block_hash: Optional[str] = None
    block_number: Optional[int] = None  # type: ignore

    """Ignored"""
    gas_limit: int = Field(0, exclude=True)
    gas_price: int = Field(0, exclude=True)
    gas_used: int = Field(0, exclude=True)
    sender: str = Field("", exclude=True)

    """Aliased"""
    txn_hash: str = Field(alias="hash")

    @validator("nonce", pre=True, allow_reuse=True)
    def validate(cls, value):
        if isinstance(value, str):
            return int(value, 16)

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
    contract_address: str
    receiver: Optional[str] = None  # type: ignore

    # Only get a receipt if deploy was accepted
    status: TransactionStatus = TransactionStatus.ACCEPTED_ON_L2

    @validator("contract_address", pre=True, allow_reuse=True)
    def validate_contract_address(cls, value):
        if isinstance(value, int):
            return to_checksum_address(value)

        return value


class InvocationReceipt(StarknetReceipt):
    actual_fee: int
    entry_point_selector: Optional[int] = Field(
        default=None, alias="selector"
    )  # Either has this or method_abi
    max_fee: int
    method_abi: Optional[MethodABI] = None  # Either has this or entry_point_selector
    receiver: str = Field(alias="contract_address")
    returndata: List[Any] = Field(default_factory=list, alias="result")
    return_value: List[int] = []

    """Aliased"""
    logs: List[dict] = Field(alias="events")

    @validator("max_fee", pre=True, allow_reuse=True)
    def validate_max_fee(cls, value):
        if isinstance(value, str):
            return int(value, 16)

        return value or 0

    @validator("entry_point_selector", pre=True, allow_reuse=True)
    def validate_entry_point_selector(cls, value):
        if isinstance(value, str):
            return int(value, 16)

        return value

    @validator("logs", pre=True, allow_reuse=True)
    def validate_logs(cls, value):
        if value and isinstance(value[0], Event):
            value = [asdict(event) for event in value]

        return value

    @property
    def ran_out_of_gas(self) -> bool:
        return self.actual_fee >= (self.max_fee or 0)

    @property
    def total_fees_paid(self) -> int:
        return self.actual_fee

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
    receiver: Optional[str] = None  # type: ignore

    # Only get a receipt if deploy was accepted
    status: TransactionStatus = TransactionStatus.ACCEPTED_ON_L2

    type: TransactionType = TransactionType.DECLARE

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
        # Look up contract type by class_hash.
        for contract_name, contract_type in self.project_manager.contracts.items():
            if not contract_type.source_id:
                continue

            program = contract_type.deployment_bytecode
            if not program:
                continue

            code = program.bytecode
            if not code:
                continue

            contract_class = ContractClass.deserialize(HexBytes(code))
            contract_cls = get_contract_class(contract_class=contract_class)
            computed_class_hash = compute_class_hash(contract_cls)
            if computed_class_hash == self.class_hash:
                return contract_type

        raise TransactionError(message="Contract type declaration was not successful.")

    def deploy(self, *args, **kwargs) -> ContractInstance:
        container = ContractContainer(self.contract_type)
        return container.deploy(*args, **kwargs)


__all__ = [
    "ContractDeclaration",
    "DeployTransaction",
    "InvokeFunctionTransaction",
    "StarknetReceipt",
    "StarknetTransaction",
]
