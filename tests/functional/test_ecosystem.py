import pytest
from ape._compat import Literal
from ape.types import AddressType
from eth_typing import HexAddress, HexStr
from ethpm_types.abi import EventABIType, MethodABI
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
    actual = list(ecosystem.decode_logs(event_abi, raw_logs))
    assert len(actual) == 1
    assert actual[0].amount == "4321"


@pytest.mark.parametrize(
    "abi, raw_data, expected",
    [
        # Array without "arr_len" exact name
        (
            CustomABI(
                outputs=[
                    EventABIType(name="response_len", type="felt"),
                    EventABIType(name="response", type="felt*"),
                ],
            ),
            [1, 1],
            [1],
        ),
        # More than 2 arguments, but no array in there
        (
            CustomABI(
                outputs=[
                    EventABIType(name="_pid", type="felt"),
                    EventABIType(name="_stable", type="felt"),
                    EventABIType(name="_token0", type="felt"),
                    EventABIType(name="_token1", type="felt"),
                    EventABIType(name="_decimals0", type="felt"),
                    EventABIType(name="_decimals1", type="felt"),
                ],
            ),
            [
                1,
                0,
                294526209724128551370299607961879888185005336491614315413210608716189734559,
                702269315989519867648921758635552661493718418630408656049459038946650527162,
                1000000000000000000,
                1000000000,
            ],
            [
                1,
                0,
                294526209724128551370299607961879888185005336491614315413210608716189734559,
                702269315989519867648921758635552661493718418630408656049459038946650527162,
                1000000000000000000,
                1000000000,
            ],
        ),
        # Uint256 with no "high" value
        (
            CustomABI(outputs=[EventABIType(name="res", type="Uint256")]),
            [63245553202367, 0],
            (63245553202367, 0),
        ),
        # Uint256 with "high" value
        (
            CustomABI(outputs=[EventABIType(name="res", type="Uint256")]),
            [42, 2],
            (42, 2),
        ),
        # Uint256 with specific value known to break old plugin version (<=0.3.0a0)
        (
            CustomABI(outputs=[EventABIType(name="balance", type="Uint256")]),
            [1, 0],
            (1, 0),
        ),
        # 1-item array of Uint256
        (
            CustomABI(
                outputs=[
                    EventABIType(name="amounts_len", type="felt"),
                    EventABIType(name="amounts", type="Uint256*"),
                ],
            ),
            [1, 123, 0],
            [(123, 0)],
        ),
        # An array of Uint256
        (
            CustomABI(
                outputs=[
                    EventABIType(name="amounts_len", type="felt"),
                    EventABIType(name="amounts", type="Uint256*"),
                ]
            ),
            [3, 123, 0, 0, 123, 123, 123],
            [(123, 0), (0, 123), (123, 123)],
        ),
        # Mix: more than 2 arguments, several arrays, and Uint256
        (
            CustomABI(
                outputs=[
                    EventABIType(name="start", type="felt"),
                    EventABIType(name="arr_len", type="felt"),
                    EventABIType(name="arr", type="felt*"),
                    EventABIType(name="some_uint256", type="Uint256"),
                    EventABIType(name="arr2_len", type="felt"),
                    EventABIType(name="arr2", type="felt*"),
                    EventABIType(name="suffix", type="felt"),
                    EventABIType(name="last_uint256", type="Uint256"),
                ],
            ),
            [
                1,  # start
                2,  # arr_len
                3,  # arr[0]
                4,  # arr[1]
                5,  # some_uint256[low]
                6,  # some_uint256[high]
                3,  # arr2_len
                8,  # arr2[0]
                9,  # arr2[1]
                10,  # arr2[2]
                11,  # suffix
                12,  # last_uint256[low]
                13,  # last_uint256[high]
            ],
            [
                1,  # start
                [3, 4],  # arr
                (5, 6),  # some_uint256
                [8, 9, 10],  # arr2
                11,  # suffix
                (12, 13),  # last_uint256
            ],
        ),
    ],
)
def test_decode_returndata(abi, raw_data, expected, ecosystem):
    assert ecosystem.decode_returndata(abi, raw_data) == expected  # type: ignore
