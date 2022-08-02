import pytest
from ape.exceptions import ApeException, ContractLogicError, OutOfGasError
from hexbytes import HexBytes
from starknet_py.net.client_errors import ClientError, ContractNotFoundError
from starknet_py.net.client_models import BlockSingleTransactionTrace
from starknet_py.transaction_exceptions import TransactionRejectedError

from ape_starknet.exceptions import StarknetProviderError
from ape_starknet.utils import (
    extract_trace_data,
    get_random_private_key,
    get_virtual_machine_error,
    is_checksum_address,
    to_checksum_address,
)


@pytest.mark.parametrize("iteration", range(10))
def test_get_random_private_key(iteration):
    pkey = get_random_private_key()
    assert len(pkey) == 66
    pkey_int = int(pkey, 16)
    pkey_back_to_str = HexBytes(pkey_int).hex()
    assert pkey_back_to_str.replace("0x", "") in pkey


def test_is_checksum_address(account):
    assert is_checksum_address(account.address)


def test_to_checksum_address(account):
    address_lowered = account.address.lower()
    actual = to_checksum_address(address_lowered)
    assert is_checksum_address(actual)
    assert actual == account.address


@pytest.mark.parametrize(
    "exception, expected",
    [
        (ApeException("Foo!"), ApeException("Foo!")),
        (
            ClientError(
                code=500,
                message=(
                    '{"message":"Error at pc=0:91:\nGot an exception '
                    "while executing a hint.\nCairo traceback (most r"
                    "ecent call last):\nUnknown location (pc=0:739)\n"
                    "Unknown location (pc=0:682)\nUnknown location (p"
                    "c=0:358)\nUnknown location (pc=0:400)\nUnknown l"
                    "ocation (pc=0:423)\n\nError in the called contra"
                    "ct (0x123):\nError at pc=0:41:\nGot an exception"
                    " while executing a hint.\nCairo traceback (most "
                    "recent call last):\nUnknown location (pc=0:7453)"
                    "\nUnknown location (pc=0:7437)\nUnknown location"
                    " (pc=0:4491)\nError message: Strings: exceeding "
                    "max felt string length (31)\nUnknown location (p"
                    "c=0:3219)\nUnknown location (pc=0:47)\n\nTraceba"
                    'ck (most recent call last):\n  File "<hint6>", l'
                    "ine 3, in <module>\nAssertionError: a = 36185027"
                    "886661312136973227830950701056231072153315966999"
                    '20561358720 is out of range.","status_code":500}'
                ),
            ),
            ContractLogicError(revert_message="Strings: exceeding max felt string length (31)"),
        ),
        (
            ContractNotFoundError(block_hash="pending"),
            StarknetProviderError("No contract found for identifier: pending"),
        ),
        (
            TransactionRejectedError(message="Actual fee exceeded max fee.\n999800000000000 > 1"),
            OutOfGasError(),
        ),
        (
            TransactionRejectedError(
                message="Error at pc=0:330:\nAn ASSERT_EQ instruction failed: 0 != 1."
            ),
            ContractLogicError(
                revert_message="Error at pc=0:330:\nAn ASSERT_EQ instruction failed: 0 != 1."
            ),
        ),
        (ValueError("Foo!"), ValueError("Foo!")),
    ],
)
def test_get_virtual_machine_error(exception, expected):
    error = get_virtual_machine_error(exception)
    assert str(error) == str(expected)


def test_extract_trace_data(traces_testnet_243810, traces_testnet_243810_results):
    for trace in traces_testnet_243810:
        trace_object = BlockSingleTransactionTrace(**trace)
        trace_data = extract_trace_data(trace_object)
        assert isinstance(trace_data, dict)

        expected_result = traces_testnet_243810_results[trace_object.transaction_hash]
        assert trace_data["result"] == expected_result
