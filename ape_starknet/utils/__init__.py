import re
from typing import Any, Dict, Optional, Tuple, Union

from ape.api.networks import LOCAL_NETWORK_NAME
from ape.exceptions import ApeException, ContractLogicError, OutOfGasError, VirtualMachineError
from ape.types import AddressType, RawAddress
from eth_typing import HexAddress, HexStr
from eth_utils import (
    add_0x_prefix,
    encode_hex,
    hexstr_if_str,
    is_text,
    keccak,
    remove_0x_prefix,
    to_hex,
)
from ethpm_types import ContractType
from hexbytes import HexBytes
from starknet_py.net.client import BadRequest
from starknet_py.net.models import TransactionType
from starknet_py.transaction_exceptions import TransactionRejectedError
from starkware.crypto.signature.signature import get_random_private_key as get_random_pkey
from starkware.starknet.definitions.general_config import StarknetChainId
from starkware.starknet.services.api.contract_class import ContractClass
from starkware.starknet.services.api.feeder_gateway.response_objects import (
    DeclareSpecificInfo,
    DeploySpecificInfo,
    InvokeSpecificInfo,
)

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
DEFAULT_ACCOUNT_SEED = 13333337


def get_chain_id(network_id: Union[str, int]) -> StarknetChainId:
    if isinstance(network_id, int):
        return StarknetChainId(network_id)

    elif network_id == LOCAL_NETWORK_NAME:
        return StarknetChainId.TESTNET  # Use TESTNET chain ID for local network

    elif network_id not in NETWORKS:
        raise ValueError(f"Unknown network '{network_id}'.")

    return StarknetChainId(NETWORKS[network_id][0])


def to_checksum_address(address: RawAddress) -> AddressType:
    try:
        hex_address = hexstr_if_str(to_hex, address)
    except AttributeError as exc:
        msg = f"Value must be any string, int, or bytes, instead got type {type(address)}"
        raise ValueError(msg) from exc

    cleaned_address = remove_0x_prefix(HexStr(hex_address))
    address_hash = encode_hex(keccak(text=cleaned_address))

    checksum_address = add_0x_prefix(
        HexStr(
            "".join(
                (hex_address[i].upper() if int(address_hash[i], 16) > 7 else hex_address[i])
                for i in range(2, len(hex_address))
            )
        )
    )

    hex_address = HexAddress(checksum_address)
    return AddressType(hex_address)


def is_hex_address(value: Any) -> bool:
    return _HEX_ADDRESS_REG_EXP.fullmatch(value) is not None if is_text(value) else False


def is_checksum_address(value: Any) -> bool:
    if not is_text(value):
        return False

    if not is_hex_address(value):
        return False

    return value == to_checksum_address(value)


def handle_client_errors(f):
    def func(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            if isinstance(result, dict) and result.get("error"):
                message = result["error"].get("message") or "Transaction failed"
                raise StarknetProviderError(message)

            return result

        except BadRequest as err:
            msg = err.text if hasattr(err, "text") else str(err)
            raise StarknetProviderError(msg) from err
        except ApeException:
            # Don't catch ApeExceptions, let them raise as they would.
            raise

        except TransactionRejectedError as err:
            vm_error = get_virtual_machine_error(err)
            if vm_error:
                raise vm_error from err

            raise  # Original exception

    return func


def get_virtual_machine_error(err: Exception) -> Optional[VirtualMachineError]:
    err_msg = str(err)

    if "rejected" not in err_msg:
        return None

    elif "actual fee exceeded max fee" in err_msg.lower():
        return OutOfGasError()  # type: ignore

    if "Error message: " in err_msg:
        err_msg = err_msg.split("Error message: ")[-1]
        if "Error at pc=" in err_msg:
            err_msg = err_msg.split("Error at pc=")[0]
    elif "error_message=" in err_msg:
        err_msg = err_msg.split("error_message=")[-1].strip("'")

    # Fix escaping newline issue with error message.
    err_msg = err_msg.replace("\\n", "").strip()
    err_msg = err_msg.replace(
        "Transaction was rejected with following starknet error: ", ""
    ).strip()
    return ContractLogicError(revert_message=err_msg)


def get_dict_from_tx_info(
    txn_info: Union[DeploySpecificInfo, InvokeSpecificInfo], **extra_kwargs
) -> Dict:
    txn_dict = {**txn_info.dump(), **extra_kwargs}
    if isinstance(txn_info, DeploySpecificInfo):
        txn_dict["contract_address"] = to_checksum_address(txn_info.contract_address)
        txn_dict["max_fee"] = 0
        txn_dict["type"] = TransactionType.DEPLOY
    elif isinstance(txn_info, InvokeSpecificInfo):
        txn_dict["contract_address"] = to_checksum_address(txn_info.contract_address)

        if "events" in txn_dict:
            txn_dict["events"] = [vars(e) for e in txn_dict["events"]]

        txn_dict["max_fee"] = txn_dict["max_fee"]

        if "method_abi" in txn_dict:
            txn_dict["method_abi"] = txn_dict.get("method_abi")

        if "entry_point_selector" in txn_dict:
            txn_dict["entry_point_selector"] = txn_dict["entry_point_selector"]

        txn_dict["type"] = TransactionType.INVOKE_FUNCTION
    elif isinstance(txn_info, DeclareSpecificInfo):
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


def from_uint(value: Tuple[int, int]) -> int:
    """Takes in Uint256-ish tuple, returns value."""
    return value[0] + (value[1] << 128)
