import itertools
from typing import Any, Dict, Iterator, List, Tuple, Type, Union

from ape.api import (
    BlockAPI,
    BlockConsensusAPI,
    BlockGasAPI,
    EcosystemAPI,
    ReceiptAPI,
    TransactionAPI,
)
from ape.contracts._utils import LogInputABICollection
from ape.exceptions import DecodingError
from ape.types import AddressType, ContractLog, RawAddress
from eth_abi.abi import decode_abi, decode_single
from eth_utils import hexstr_if_str, is_0x_prefixed, keccak, to_bytes
from ethpm_types.abi import ConstructorABI, EventABI, EventABIType, MethodABI
from hexbytes import HexBytes
from starknet_py.net.models.address import parse_address  # type: ignore
from starknet_py.net.models.chains import StarknetChainId  # type: ignore
from starknet_py.utils.data_transformer import DataTransformer  # type: ignore
from starkware.starknet.definitions.fields import ContractAddressSalt  # type: ignore
from starkware.starknet.definitions.transaction_type import TransactionType  # type: ignore
from starkware.starknet.public.abi_structs import identifier_manager_from_abi  # type: ignore
from starkware.starknet.services.api.contract_definition import ContractDefinition  # type: ignore

from ape_starknet._utils import to_checksum_address
from ape_starknet.exceptions import StarknetEcosystemError
from ape_starknet.transactions import (
    DeployTransaction,
    InvokeFunctionTransaction,
    StarknetReceipt,
    StarknetTransaction,
)

NETWORKS = {
    # chain_id, network_id
    "mainnet": (StarknetChainId.MAINNET.value, StarknetChainId.MAINNET.value),
    "testnet": (StarknetChainId.TESTNET.value, StarknetChainId.TESTNET.value),
}


class StarknetBlock(BlockAPI):
    gas_data: BlockGasAPI = None  # type: ignore
    consensus_data: BlockConsensusAPI = None  # type: ignore


class Starknet(EcosystemAPI):
    """
    The Starknet ``EcosystemAPI`` implementation.
    """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"

    @classmethod
    def decode_address(cls, raw_address: RawAddress) -> AddressType:
        """
        Make a checksum address given a supported format.
        Borrowed from ``eth_utils.to_checksum_address()`` but supports
        non-length 42 addresses.

        Args:
            value (Union[int, str, bytes]): The value to convert.

        Returns:
            ``AddressType``: The converted address.
        """
        return to_checksum_address(raw_address)

    @classmethod
    def encode_address(cls, address: AddressType) -> RawAddress:
        return parse_address(address)

    def serialize_transaction(self, transaction: TransactionAPI) -> bytes:
        if not isinstance(transaction, StarknetTransaction):
            raise StarknetEcosystemError(f"Can only serialize '{StarknetTransaction.__name__}'.")

        starknet_object = transaction.as_starknet_object()
        return starknet_object.deserialize()

    def decode_return_data(self, abi: MethodABI, raw_data: bytes) -> List[Any]:
        # TODO: I think this may only handle integers right now
        return raw_data  # type: ignore

    def encode_call_data(
        self, full_abi: List, entry_point_abi: Dict, call_args: Union[List, Tuple]
    ) -> List:
        id_manager = identifier_manager_from_abi(full_abi)
        transformer = DataTransformer(entry_point_abi, id_manager)

        cleaned_args = []
        for arg in call_args:
            if isinstance(arg, str) and is_0x_prefixed(arg):
                cleaned_args.append(int(arg, 16))
            elif isinstance(arg, HexBytes):
                cleaned_args.append(int(arg.hex(), 16))
            else:
                cleaned_args.append(arg)

        calldata, _ = transformer.from_python(*cleaned_args)
        return calldata

    def decode_receipt(self, data: dict) -> ReceiptAPI:
        txn_type = data["type"]

        if txn_type == TransactionType.INVOKE_FUNCTION.value:
            data["receiver"] = data.pop("contract_address")

        return StarknetReceipt(
            provider=data.get("provider"),
            type=data["type"],
            transaction_hash=data["transaction_hash"],
            status=data["status"].value,
            block_number=data["block_number"],
            events=data.get("events", []),
            contract_address=data.get("contract_address"),
            receiver=data.get("receiver", ""),  # TODO: What should receiver be when Deploy?
        )

    def decode_block(self, data: dict) -> BlockAPI:
        return StarknetBlock(
            number=data["block_number"],
            hash=HexBytes(data["block_hash"]),
            parent_hash=HexBytes(data["parent_block_hash"]),
            size=len(data["transactions"]),  # TODO: Figure out size
            timestamp=data["timestamp"],
        )

    def encode_deployment(
        self, deployment_bytecode: HexBytes, abi: ConstructorABI, *args, **kwargs
    ) -> TransactionAPI:
        salt = kwargs.get("salt")
        if not salt:
            salt = ContractAddressSalt.get_random_value()

        contract = ContractDefinition.deserialize(deployment_bytecode)
        calldata = self.encode_call_data(contract.abi, abi.dict(), args)
        return DeployTransaction(
            salt=salt, constructor_calldata=calldata, contract_code=contract.dumps()
        )

    def encode_transaction(
        self, address: AddressType, abi: MethodABI, *args, **kwargs
    ) -> TransactionAPI:
        return InvokeFunctionTransaction(
            contract_address=address,
            method_abi=abi,
            calldata=args,
            sender=kwargs.get("sender"),
            max_fee=kwargs.get("max_fee", 0),
        )

    def create_transaction(self, **kwargs) -> TransactionAPI:
        txn_type = kwargs.pop("type")
        txn_cls: Union[Type[InvokeFunctionTransaction], Type[DeployTransaction]]
        if txn_type == TransactionType.INVOKE_FUNCTION:
            txn_cls = InvokeFunctionTransaction
        elif txn_type == TransactionType.DEPLOY:
            txn_cls = DeployTransaction

        return txn_cls(**kwargs)

    def decode_logs(self, abi: EventABI, data: List[Dict]) -> Iterator[ContractLog]:
        if not abi.anonymous:
            event_id_bytes = keccak(to_bytes(text=abi.selector))
            matching_logs = [log for log in data if log["topics"][0] == event_id_bytes]
        else:
            matching_logs = data

        topics_list: List[EventABIType] = []
        data_list: List[EventABIType] = []
        for abi_input in abi.inputs:
            if abi_input.indexed:
                topics_list.append(abi_input)
            else:
                data_list.append(abi_input)

        abi_topics = LogInputABICollection(abi, topics_list)
        abi_data = LogInputABICollection(abi, data_list)

        duplicate_names = set(abi_topics.names).intersection(abi_data.names)
        if duplicate_names:
            duplicate_names_str = ", ".join([n for n in duplicate_names if n])
            raise DecodingError(
                "The following argument names are duplicated "
                f"between event inputs: '{duplicate_names_str}'."
            )

        for log in matching_logs:
            indexed_data = log["topics"] if log.get("anonymous", False) else log["topics"][1:]
            log_data = hexstr_if_str(to_bytes, log["data"])  # type: ignore

            if len(indexed_data) != len(abi_topics.types):
                raise DecodingError(
                    f"Expected '{len(indexed_data)}' log topics.  Got '{len(abi_topics.types)}'."
                )

            decoded_topic_data = [
                decode_single(topic_type, topic_data)  # type: ignore
                for topic_type, topic_data in zip(abi_topics.types, indexed_data)
            ]
            decoded_log_data = decode_abi(abi_data.types, log_data)  # type: ignore
            event_args = dict(
                itertools.chain(
                    zip(abi_topics.names, decoded_topic_data),
                    zip(abi_data.names, decoded_log_data),
                )
            )
            yield ContractLog(  # type: ignore
                name=abi.name,
                index=log["logIndex"],
                event_arguments=event_args,
                transaction_hash=log["transactionHash"],
                block_hash=log["blockHash"],
                block_number=log["blockNumber"],
            )  # type: ignore
