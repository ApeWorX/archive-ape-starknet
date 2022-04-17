import pytest
from eth_utils import remove_0x_prefix
from starkware.cairo.lang.vm.cairo_runner import pedersen_hash  # type: ignore

from ape_starknet._utils import is_hex_address

from ..conftest import PASSWORD, PUBLIC_KEY


def test_address(existing_key_file_account):
    expected = PUBLIC_KEY
    actual = existing_key_file_account.address
    assert actual != expected, "Result is not checksummed"
    assert remove_0x_prefix(actual.lower()) == expected
    assert is_hex_address(actual)


def test_sign_message_using_key_file_account(existing_key_file_account):
    assert existing_key_file_account.sign_message(5, passphrase=PASSWORD)


def test_contact_address(account):
    address = account.contract_address
    assert is_hex_address(address)


def test_sign_message_and_check_signature(account):
    data = 500
    signature = account.sign_message(data)
    data_hash = pedersen_hash(data, 0)
    result = account.check_signature(data_hash, signature)
    assert result, "Failed to validate signature"


@pytest.mark.parametrize(
    "get_address",
    [
        lambda a, _: a.address,
        lambda a, e: e.encode_address(a.address),
        lambda a, _: a.contract_address,
        lambda a, e: e.encode_address(a.contract_address),
    ],
)
def test_access_account_by_str_address(account, account_container, ecosystem, get_address):
    address = get_address(account, ecosystem)
    assert account_container[address] == account
    assert address in account_container


def test_balance(account):
    assert account.balance == 0
