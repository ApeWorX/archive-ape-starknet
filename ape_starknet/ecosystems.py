from typing import Any, Dict, Iterator, List, Tuple, Type, Union

from ape.api import (
    BlockAPI,
    BlockConsensusAPI,
    BlockGasAPI,
    EcosystemAPI,
    ReceiptAPI,
    TransactionAPI,
)
from ape.types import AddressType, ContractLog, RawAddress
from eth_utils import is_0x_prefixed
from ethpm_types.abi import ConstructorABI, EventABI, MethodABI
from hexbytes import HexBytes
from starknet_py.net.models.address import parse_address  # type: ignore
from starknet_py.net.models.chains import StarknetChainId  # type: ignore
from starknet_py.utils.data_transformer import DataTransformer  # type: ignore
from starkware.starknet.definitions.fields import ContractAddressSalt  # type: ignore
from starkware.starknet.definitions.transaction_type import TransactionType  # type: ignore
from starkware.starknet.public.abi_structs import identifier_manager_from_abi  # type: ignore
from starkware.starknet.services.api.contract_class import ContractClass  # type: ignore

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
            raw_address (Union[int, str, bytes]): The value to convert.

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

    def decode_returndata(self, abi: MethodABI, raw_data: List[int]) -> List[Any]:  # type: ignore
        def clear_lengths(arr):
            arr_len = arr[0]
            rest = arr[1:]
            num_rest = len(rest)
            return clear_lengths(rest) if arr_len == num_rest else arr

        is_arr = abi.outputs[0].name == "arr_len" and abi.outputs[1].type == "felt*"
        has_leftover_length = len(raw_data) > 1 and not is_arr
        if (
            len(abi.outputs) == 2
            and is_arr
            and len(raw_data) >= 2
            and all([isinstance(i, int) for i in raw_data])
        ) or has_leftover_length:
            # Is array - check if need to strip off arr_len
            return clear_lengths(raw_data)

        return raw_data

    def encode_calldata(
        self,
        full_abi: List,
        method_abi: Union[ConstructorABI, MethodABI],
        call_args: Union[List, Tuple],
    ) -> List:
        id_manager = identifier_manager_from_abi(full_abi)
        transformer = DataTransformer(method_abi.dict(), id_manager)
        encoded_args = []
        index = 0
        last_index = len(method_abi.inputs) - 1
        for call_arg, input_type in zip(call_args, method_abi.inputs):
            if str(input_type.type).endswith("*"):
                # (arrays) Was processed the iteration before.
                continue

            elif (
                input_type.name == "arr_len"
                and index < last_index
                and str(method_abi.inputs[index + 1].type).endswith("*")
            ):
                # Handle arrays.
                array_arg = [self.encode_primitive_value(v) for v in call_args[index + 1]]
                encoded_args.append(array_arg)

            else:
                encoded_arg = self.encode_primitive_value(call_arg)
                encoded_args.append(encoded_arg)

            index += 1

        calldata, _ = transformer.from_python(*encoded_args)
        return calldata

    def encode_primitive_value(self, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            return [self.encode_primitive_value(v) for v in value]
        if isinstance(value, str) and is_0x_prefixed(value):
            return int(value, 16)
        elif isinstance(value, HexBytes):
            return int(value.hex(), 16)

        return value

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
            block_hash=data["block_hash"],
            events=data.get("events", []),
            contract_address=data.get("contract_address"),
            receiver=data.get("receiver", ""),
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

        contract = ContractClass.deserialize(deployment_bytecode)
        calldata = self.encode_calldata(contract.abi, abi, args)
        return DeployTransaction(
            salt=salt,
            constructor_calldata=calldata,
            contract_code=contract.dumps(),
            token=kwargs.get("token"),
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

    def decode_logs(self, abi: EventABI, raw_logs: List[Dict]) -> Iterator[ContractLog]:
        index = 0
        for log in raw_logs:
            event_args = dict(zip([a.name for a in abi.inputs], log["data"]))
            yield ContractLog(  # type: ignore
                name=abi.name,
                index=index,
                event_arguments=event_args,
                transaction_hash=log["transaction_hash"],
                block_hash=log["block_hash"],
                block_number=log["block_number"],
            )  # type: ignore
            index += 1
