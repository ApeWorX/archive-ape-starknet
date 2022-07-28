import pytest
from ape._compat import Literal
from ape.types import AddressType
from eth_typing import HexAddress, HexStr
from ethpm_types.abi import MethodABI
from hexbytes import HexBytes
from starkware.starknet.public.abi import get_selector_from_name

INT_ADDRESS = 269168490721327376227480949634158339134330130662514218728945045982440529971
STR_ADDRESS = "0x0098580e36aB1485C66f0DC95C2c923e734B7Af44D04dD2B5b9d0809Aa672033"
HEXBYTES_ADDRESS = HexBytes(STR_ADDRESS)
EVENT_NAME = "balance_increased"


class CustomABI(MethodABI):
    name: str = "Custom"
    type: Literal["function"] = "function"


@pytest.fixture(scope="module")
def raw_logs():
    return [
        {
            "data": ["4321"],
            "from_address": "0x14acf3b7e92f97adee4d5359a7de3d673582f0ce03d33879cdbdbf03ec7fa5d",
            "keys": [get_selector_from_name(EVENT_NAME)],
            "transaction_hash": "0x7ccac756aafe0df416ee4f4ca74b42cdd7399ebae5aa31d92132dfbee445370",
            "block_number": 5,
            "block_hash": "0x7032c67f8741c6ce547175c2101d5ccdf468ca6ea0642bafccea04080726a06",
        }
    ]


@pytest.fixture(scope="module")
def event_abi(contract):
    return contract.balance_increased.abi


@pytest.mark.parametrize("value", (INT_ADDRESS, STR_ADDRESS, HEXBYTES_ADDRESS))
def test_encode_and_decode_address(value, ecosystem):
    decoded_address = ecosystem.decode_address(value)
    expected = AddressType(HexAddress(HexStr(STR_ADDRESS)))
    assert decoded_address == expected

    # The values should _always_ encode back to the INT_ADDRESS.
    re_encoded_address = ecosystem.encode_address(decoded_address)
    assert re_encoded_address == INT_ADDRESS


def test_decode_logs(ecosystem, event_abi, raw_logs):
    actual = list(ecosystem.decode_logs(raw_logs, event_abi))
    assert len(actual) == 1
    assert actual[0].amount == "4321"
