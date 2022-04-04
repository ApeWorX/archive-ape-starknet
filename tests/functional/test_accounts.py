from eth_utils import remove_0x_prefix
from starkware.cairo.lang.vm.cairo_runner import pedersen_hash  # type: ignore

from ..conftest import PUBLIC_KEY


def test_address(existing_key_file_account):
    expected = PUBLIC_KEY
    actual = existing_key_file_account.address
    assert actual != expected, "Result is not checksummed"
    assert actual.startswith("0x")
    assert remove_0x_prefix(actual.lower()) == expected


def test_sign_message_and_check_signature(account):
    data = 500
    signature = account.sign_message(data)
    data_hash = pedersen_hash(data, 0)
    result = account.check_signature(data_hash, signature)
    assert result, "Failed to validate signature"
