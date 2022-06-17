import re
from typing import Any, Optional, Union

from ape.api.networks import LOCAL_NETWORK_NAME
from ape.exceptions import ApeException, ContractLogicError, ProviderError, VirtualMachineError
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
from starknet_py.net.client import BadRequest  # type: ignore
from starkware.starknet.definitions.general_config import StarknetChainId  # type: ignore

PLUGIN_NAME = "starknet"
NETWORKS = {
    # chain_id, network_id
    "mainnet": (StarknetChainId.MAINNET.value, StarknetChainId.MAINNET.value),
    "testnet": (StarknetChainId.TESTNET.value, StarknetChainId.TESTNET.value),
}
_HEX_ADDRESS_REG_EXP = re.compile("(0x)?[0-9a-f]*", re.IGNORECASE | re.ASCII)
"""Same as from eth-utils except not limited length."""
ALPHA_MAINNET_WL_DEPLOY_TOKEN_KEY = "ALPHA_MAINNET_WL_DEPLOY_TOKEN"


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


def handle_client_errors(f):
    def func(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            if isinstance(result, dict) and result.get("error"):
                message = result["error"].get("message") or "Transaction failed"
                raise ProviderError(message)

            return result

        except BadRequest as err:
            msg = err.text if hasattr(err, "text") else str(err)
            raise ProviderError(msg) from err
        except ApeException:
            # Don't catch ApeExceptions, let them raise as they would.
            raise
        except Exception as err:
            vm_error = get_virtual_machine_error(err)
            if vm_error:
                raise vm_error from err

            raise  # Original exception

    return func


def get_virtual_machine_error(err: Exception) -> Optional[VirtualMachineError]:
    err_msg = str(err)
    if "rejected" not in err_msg:
        return None

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
