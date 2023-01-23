import asyncio
import re
from asyncio import gather
from dataclasses import asdict
from json import JSONDecodeError, loads
from typing import Any, Dict, List, Optional, Union, cast

from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractEvent
from ape.exceptions import (
    ApeException,
    ContractError,
    ContractLogicError,
    OutOfGasError,
    SignatureError,
)
from ape.logging import logger
from ape.types import AddressType, RawAddress
from eth_typing import HexAddress, HexStr
from eth_utils import add_0x_prefix, is_0x_prefixed, is_hex, is_text, remove_0x_prefix, to_hex
from eth_utils import to_int as eth_to_int
from ethpm_types import ContractType
from ethpm_types.abi import EventABI, MethodABI
from hexbytes import HexBytes
from starknet_py.net import KeyPair
from starknet_py.net.client_errors import ClientError
from starknet_py.net.client_models import (
    BlockSingleTransactionTrace,
    DeclareTransaction,
    DeployAccountTransaction,
    InvokeTransaction,
    Transaction,
)
from starknet_py.net.models import TransactionType
from starknet_py.net.models.address import parse_address
from starknet_py.transaction_exceptions import TransactionRejectedError
from starkware.cairo.bootloaders.compute_fact import keccak_ints
from starkware.crypto.signature.signature import get_random_private_key as get_random_pkey
from starkware.starknet.core.os.class_hash import compute_class_hash
from starkware.starknet.definitions.general_config import StarknetChainId
from starkware.starknet.public.abi import get_selector_from_name
from starkware.starknet.services.api.contract_class import ContractClass
from starkware.starknet.third_party.open_zeppelin.starknet_contracts import account_contract

from ape_starknet.exceptions import StarknetProviderError
from ape_starknet.utils.basemodel import create_contract_class

PLUGIN_NAME = "starknet"
NETWORKS = {
    # chain_id, network_id
    "mainnet": (StarknetChainId.MAINNET.value, StarknetChainId.MAINNET.value),
    "testnet": (StarknetChainId.TESTNET.value, StarknetChainId.TESTNET.value),
    "testnet2": (StarknetChainId.TESTNET2.value, StarknetChainId.TESTNET.value),
}
_HEX_ADDRESS_REG_EXP = re.compile("(0x)?[0-9a-f]*", re.IGNORECASE | re.ASCII)
"""Same as from eth-utils except not limited length."""
ALPHA_MAINNET_WL_DEPLOY_TOKEN_KEY = "ALPHA_MAINNET_WL_DEPLOY_TOKEN"
EXECUTE_METHOD_NAME = "__execute__"
EXECUTE_SELECTOR = get_selector_from_name(EXECUTE_METHOD_NAME)
DEFAULT_ACCOUNT_SEED = 2147483647  # Prime
ContractEventABI = Union[List[Union[EventABI, ContractEvent]], Union[EventABI, ContractEvent]]
MAX_FEE = int(1e20)
_DECLARE_ERROR_PATTERN = re.compile(r"Class with hash (0x[0-9a-fA-F]+) is not declared")
STARKNET_FEE_TOKEN_SYMBOL = "ETH"
_CLIENT_FAILED_PREFIX_PATTERN = re.compile(r"Client failed( with code \d+)?: (.*)")


def convert_contract_class_to_contract_type(
    name: str, source_id: str, contract_class: ContractClass
):
    return ContractType.parse_obj(
        {
            "contractName": name,
            "sourceId": source_id,
            "deploymentBytecode": {"bytecode": contract_class.serialize().hex()},
            "runtimeBytecode": {},
            "abi": contract_class.abi,
        }
    )


OPEN_ZEPPELIN_ACCOUNT_SOURCE_ID = "openzeppelin/account/Account.cairo"
OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE = convert_contract_class_to_contract_type(
    "Account", OPEN_ZEPPELIN_ACCOUNT_SOURCE_ID, account_contract
)
OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH = compute_class_hash(account_contract)
EXECUTE_ABI = OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE.mutable_methods[EXECUTE_METHOD_NAME]

# Taken from https://github.com/argentlabs/argent-x/blob/develop/packages/extension/src/background/wallet.ts  # noqa: E501
ARGENTX_ACCOUNT_CLASS_HASH = int(
    "0x025ec026985a3bf9d0cc1fe17326b245dfdc3ff89b8fde106542a3ea56c5a918", 16
)
ARGENTX_ACCOUNT_SOURCE_ID = "account/ArgentAccount.cairo"
DEVNET_ACCOUNT_START_BALANCE = 1000000000000000000000


def get_chain_id(network_id: Union[str, int]) -> StarknetChainId:
    if isinstance(network_id, int):
        return StarknetChainId(network_id)

    elif network_id == LOCAL_NETWORK_NAME:
        return StarknetChainId.TESTNET  # Use TESTNET chain ID for local network

    elif network_id not in NETWORKS:
        raise StarknetProviderError(f"Unknown network '{network_id}'.")

    return StarknetChainId(NETWORKS[network_id][0])


def to_checksum_address(address: RawAddress) -> AddressType:
    if is_checksum_address(address):
        return cast(AddressType, address)

    return _to_checksum_address(address)


def _to_checksum_address(address: RawAddress) -> AddressType:
    if isinstance(address, bytes):
        address = HexBytes(address).hex()

    address_int = parse_address(address)
    address_str = pad_hex_str(HexBytes(address_int).hex().lower())
    chars = [c for c in remove_0x_prefix(HexStr(address_str))]
    hashed = [b for b in HexBytes(keccak_ints([address_int]))]

    for i in range(0, len(chars), 2):
        try:
            if hashed[i >> 1] >> 4 >= 8:
                chars[i] = chars[i].upper()
            if (hashed[i >> 1] & 0x0F) >= 8:
                chars[i + 1] = chars[i + 1].upper()
        except IndexError:
            continue

    rejoined_address_str = add_0x_prefix(HexStr("".join(chars)))
    return AddressType(HexAddress(HexStr(rejoined_address_str)))


def is_hex_address(value: Any) -> bool:
    return _HEX_ADDRESS_REG_EXP.fullmatch(value) is not None if is_text(value) else False


def is_checksum_address(value: Any) -> bool:
    if not is_text(value):
        return False

    if not is_hex_address(value):
        return False

    return value == _to_checksum_address(value)


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
    invocation_result = trace_data["result"]
    internal_calls = trace_data["internal_calls"]
    trace_data["result"] = (
        internal_calls[-1]["result"] if internal_calls else invocation_result
    ) or invocation_result
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
            new_err = handle_client_error(err)
            if new_err:
                raise new_err from err

            raise  # Original error

    return func


def handle_client_error(err: Exception) -> Optional[Exception]:
    if isinstance(err, ApeException) or not isinstance(
        err, (ClientError, TransactionRejectedError)
    ):
        return err

    err_msg = err.message
    if "Actual fee exceeded max fee" in err_msg:
        return OutOfGasError()

    maybe_contract_logic_error = False
    if "Error message:" in err_msg:
        err_msg = err_msg.split("Error message:")[-1].splitlines()[0].strip().split("\\n")[0]
        maybe_contract_logic_error = True

    elif "Error at pc=" in err_msg:
        err_msg = err_msg.strip().replace("\\n", " ")
        err_msg = _try_extract_message_from_json(err_msg)
        maybe_contract_logic_error = True

    if "INVALID_SIGNATURE_LENGTH" in err_msg:
        return SignatureError("Invalid signature length.")

    elif "UNINITIALIZED_CONTRACT" in err_msg and "is not deployed" in err_msg:
        address = err_msg.split("is not deployed")[0].strip().split(" ")[-1]
        if is_hex(address):
            return ContractError(f"Contract at address '{address}' not deployed.")

    elif "Signature" in err_msg and "is invalid, with respect to the public key" in err_msg:
        message = "Invalid signature"
        parts = err_msg.split("public key ")
        if len(parts) == 2:
            key_str = parts[-1].split(" ")[0].rstrip(",")
            if key_str.isnumeric():
                key = to_hex(int(key_str))
                message = f"{message} with respect to public key {key}"

        return SignatureError(f"{message}.")

    declare_error_search = _DECLARE_ERROR_PATTERN.search(err_msg)
    if declare_error_search:
        address = declare_error_search.groups()[0]
        return StarknetProviderError(f"Contract with address '{address}' not declared.")

    elif maybe_contract_logic_error:
        return ContractLogicError(revert_message=err_msg)

    err_msg = err_msg.strip().rstrip(".")
    match = _CLIENT_FAILED_PREFIX_PATTERN.match(err_msg)
    if match:
        groups = match.groups()
        if groups:
            trimmed = groups[-1]
            if trimmed:
                err_msg = trimmed

    if err_msg.endswith("\n."):
        err_msg = "\n.".join(err_msg.split("\n.")[:-1])

    err_msg = _try_extract_message_from_json(err_msg)

    if not err_msg.endswith("."):
        err_msg = f"{err_msg}."

    return StarknetProviderError(err_msg)


def _try_extract_message_from_json(value: str) -> str:
    try:
        msg_dict = loads(value)
    except JSONDecodeError:
        return value

    if "message" in msg_dict:
        return msg_dict["message"]

    return value


def get_dict_from_tx_info(txn_info: Transaction) -> Dict:
    txn_dict = {**asdict(txn_info)}
    if isinstance(txn_info, InvokeTransaction):
        txn_dict["type"] = TransactionType.INVOKE_FUNCTION
    elif isinstance(txn_info, DeclareTransaction):
        txn_dict["type"] = TransactionType.DECLARE
    elif isinstance(txn_info, DeployAccountTransaction):
        txn_dict["type"] = TransactionType.DEPLOY_ACCOUNT

    return txn_dict


def get_method_abi_from_selector(
    selector: Union[str, int], contract_type: ContractType
) -> MethodABI:
    # TODO: Properly integrate with ethpm-types

    if isinstance(selector, str):
        selector = int(selector, 16)

    for abi in contract_type.mutable_methods:
        selector_to_check = get_selector_from_name(abi.name)

        if selector == selector_to_check:
            return abi

    raise ContractError(f"Method '{selector}' not found in '{contract_type.name}'.")


def get_random_private_key() -> str:
    private_key = HexBytes(get_random_pkey()).hex()
    return pad_hex_str(private_key)


def pad_hex_str(value: str, to_length: int = 64) -> str:
    val = value.replace("0x", "")
    actual_len = len(val)
    padding = "0" * (to_length - actual_len)
    return f"0x{padding}{val}"


def run_until_complete(*coroutine):
    coroutines = list(coroutine)
    if len(coroutines) > 1:
        task = gather(*coroutine, return_exceptions=True)
    else:
        task = coroutines[0]

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(task)
    return result


def to_int(val: Any) -> int:
    if isinstance(val, int):
        return val

    elif isinstance(val, str) and is_0x_prefixed(val):
        return eth_to_int(hexstr=val)

    elif isinstance(val, str) and val.isnumeric():
        return int(val)

    elif isinstance(val, str):
        return eth_to_int(val.encode())

    elif hasattr(val, "address"):
        return to_int(val.address)

    return eth_to_int(val)


def get_class_hash(code: Union[str, HexBytes]):
    contract_class = create_contract_class(code)
    return compute_class_hash(contract_class)


def create_keypair(private_key: Union[str, int]) -> KeyPair:
    # Validate private key.
    if isinstance(private_key, str) and is_0x_prefixed(private_key):
        private_key = to_int(private_key.strip("'\""))
    elif isinstance(private_key, str):
        private_key = to_int(private_key)

    return KeyPair.from_private_key(private_key)


def get_account_constructor_calldata(key_pair: KeyPair, class_hash: int) -> List[Any]:
    # Use known ctor data
    if class_hash == OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH:
        return [key_pair.public_key]
    elif class_hash == ARGENTX_ACCOUNT_CLASS_HASH:
        return []
    else:
        logger.warning(f"Constructor calldata for account with class '{class_hash}' not known.")
        return []
