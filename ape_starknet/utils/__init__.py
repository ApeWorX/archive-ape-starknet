import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Union

from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractEvent
from ape.exceptions import ApeException, ContractLogicError, OutOfGasError
from ape.types import AddressType, RawAddress
from eth_typing import HexAddress, HexStr
from eth_utils import add_0x_prefix, is_text, remove_0x_prefix
from ethpm_types import ContractType
from ethpm_types.abi import EventABI
from hexbytes import HexBytes
from starknet_py.net.client_errors import ClientError
from starknet_py.net.client_models import (
    BlockSingleTransactionTrace,
    DeclareTransaction,
    DeployTransaction,
    InvokeTransaction,
    Transaction,
)
from starknet_py.net.models import TransactionType
from starknet_py.net.models.address import parse_address
from starknet_py.transaction_exceptions import TransactionRejectedError
from starkware.crypto.signature.fast_pedersen_hash import pedersen_hash
from starkware.crypto.signature.signature import get_random_private_key as get_random_pkey
from starkware.starknet.definitions.general_config import StarknetChainId
from starkware.starknet.services.api.contract_class import ContractClass

from ape_starknet.exceptions import StarknetProviderError

PLUGIN_NAME = "starknet"
NETWORKS = {
    # chain_id, network_id
    "mainnet": (StarknetChainId.MAINNET.value, StarknetChainId.MAINNET.value),
    "testnet": (StarknetChainId.TESTNET.value, StarknetChainId.TESTNET.value),
}
_HEX_ADDRESS_REG_EXP = re.compile("(0x)?[0-9a-f]*", re.IGNORECASE | re.ASCII)
"""Same as from eth-utils except not limited length."""
ALPHA_MAINNET_WL_DEPLOY_TOKEN_KEY = "ALPHA_MAINNET_WL_DEPLOY_TOKEN"
DEFAULT_ACCOUNT_SEED = 2147483647  # Prime
ContractEventABI = Union[List[Union[EventABI, ContractEvent]], Union[EventABI, ContractEvent]]


def get_chain_id(network_id: Union[str, int]) -> StarknetChainId:
    if isinstance(network_id, int):
        return StarknetChainId(network_id)

    elif network_id == LOCAL_NETWORK_NAME:
        return StarknetChainId.TESTNET  # Use TESTNET chain ID for local network

    elif network_id not in NETWORKS:
        raise StarknetProviderError(f"Unknown network '{network_id}'.")

    return StarknetChainId(NETWORKS[network_id][0])


def to_checksum_address(address: RawAddress) -> AddressType:
    if isinstance(address, bytes):
        address = HexBytes(address).hex()

    address_int = parse_address(address)
    address_str = pad_hex_str(HexBytes(address_int).hex().lower())
    chars = [c for c in remove_0x_prefix(HexStr(address_str))]
    hashed = [b for b in HexBytes(pedersen_hash(0, address_int))]

    for i in range(0, len(chars), 2):
        try:
            if hashed[i >> 1] >> 4 >= 8:
                chars[i] = chars[i].upper()
            if (hashed[i >> 1] & 0x0F) >= 8:
                chars[i + 1] = chars[i + 1].upper()
        except IndexError:
            continue

    return AddressType(HexAddress(add_0x_prefix(HexStr("".join(chars)))))


def is_hex_address(value: Any) -> bool:
    return _HEX_ADDRESS_REG_EXP.fullmatch(value) is not None if is_text(value) else False


def is_checksum_address(value: Any) -> bool:
    if not is_text(value):
        return False

    if not is_hex_address(value):
        return False

    return value == to_checksum_address(value)


def extract_trace_data(trace: BlockSingleTransactionTrace) -> Dict[str, Any]:
    if not trace:
        return {}

    trace_data = trace.function_invocation

    # Keep the most relevant `result`: given the account implementation, `result`
    # may contain an additional number prepend to the data to expose the total
    # number of items. For a method returning a 3-items array like `[1, 2, 3]`,
    # in such scenario `results` would be `[0x4, 0x3, 0x1, 0x2, 0x3]` (the prepend
    # number: 4, the array length: 3, then array items: 1, 2, and 3).
    # As there is no known way to guess when to remove such a number, we prefer to "scan"
    # trace internals to select the most appropriate result. For instance, when `result`
    # contains the additional value, we just need to use the "internal call" `result`
    # that will contain the exact value the method returned.
    invokation_result = trace_data["result"]
    internal_calls = trace_data["internal_calls"]
    trace_data["result"] = (
        internal_calls[-1]["result"] if internal_calls else invokation_result
    ) or invokation_result

    return trace_data


def handle_client_errors(f):
    def func(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            if isinstance(result, dict) and result.get("error"):
                message = result["error"].get("message") or "Transaction failed"
                raise StarknetProviderError(message)

            return result

        except Exception as err:
            raise get_virtual_machine_error(err) from err

    return func


def get_virtual_machine_error(err: Exception) -> Optional[Exception]:
    if isinstance(err, ApeException) or not isinstance(
        err, (ClientError, TransactionRejectedError)
    ):
        return err

    err_msg = err.message

    if "Actual fee exceeded max fee" in err_msg:
        return OutOfGasError()

    if isinstance(err, ClientError):
        # Remove https://github.com/software-mansion/starknet.py/blob/0.4.3-alpha/starknet_py/net/client_errors.py#L11 # noqa
        err_msg = err_msg.split(":", 1)[-1]

    if "Error message:" in err_msg:
        err_msg = err_msg.split("Error message:")[-1].splitlines()[0]
        return ContractLogicError(revert_message=err_msg.strip())

    if "Error at pc=" in err_msg:
        return ContractLogicError(revert_message=err_msg.strip())

    return StarknetProviderError(err_msg.strip())


def get_dict_from_tx_info(txn_info: Transaction, **extra_kwargs) -> Dict:
    txn_dict = {**asdict(txn_info), **extra_kwargs}

    if isinstance(txn_info, DeployTransaction):
        txn_dict["contract_address"] = to_checksum_address(txn_info.contract_address)
        txn_dict["max_fee"] = 0
        txn_dict["type"] = TransactionType.DEPLOY
    elif isinstance(txn_info, InvokeTransaction):
        txn_dict["contract_address"] = to_checksum_address(txn_info.contract_address)
        txn_dict["events"] = [vars(e) for e in txn_dict.get("events", [])]
        txn_dict["type"] = TransactionType.INVOKE_FUNCTION
    elif isinstance(txn_info, DeclareTransaction):
        txn_dict["sender"] = to_checksum_address(txn_info.sender_address)
        txn_dict["type"] = TransactionType.DECLARE

    return txn_dict


def convert_contract_class_to_contract_type(contract_class: ContractClass):
    return ContractType.parse_obj(
        {
            "contractName": "Account",
            "sourceId": "openzeppelin.account.Account.cairo",
            "deploymentBytecode": {"bytecode": contract_class.serialize().hex()},
            "runtimeBytecode": {},
            "abi": contract_class.abi,
        }
    )


def get_random_private_key() -> str:
    private_key = HexBytes(get_random_pkey()).hex()
    return pad_hex_str(private_key)


def pad_hex_str(value: str, to_length: int = 66) -> str:
    val = value.replace("0x", "")
    actual_len = len(val)
    padding = "0" * (to_length - 2 - actual_len)
    return f"0x{padding}{val}"
