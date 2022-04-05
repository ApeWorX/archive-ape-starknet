import io

from eth_utils import remove_0x_prefix
from starkware.cairo.lang.vm.cairo_runner import pedersen_hash  # type: ignore

from ape_starknet._utils import is_hex_address

from ..conftest import PUBLIC_KEY


def test_address(existing_key_file_account):
    expected = PUBLIC_KEY
    actual = existing_key_file_account.address
    assert actual != expected, "Result is not checksummed"
    assert remove_0x_prefix(actual.lower()) == expected
    assert is_hex_address(actual)


def test_sign_message_using_key_file_account(existing_key_file_account, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("a\ny"))
    assert existing_key_file_account.sign_message(5)

    # Ensure uses cached key by not requiring stdin again.
    assert existing_key_file_account.sign_message(6)


def test_contact_address(account):
    address = account.contract_address
    assert is_hex_address(address)


def test_sign_message_and_check_signature(account):
    data = 500
    signature = account.sign_message(data)
    data_hash = pedersen_hash(data, 0)
    result = account.check_signature(data_hash, signature)
    assert result, "Failed to validate signature"


def test_access_account_by_address(account, account_container, ecosystem):
    actual = account_container[account.address]
    assert actual == account

    # Ensure also works with int version of address
    address = ecosystem.encode_address(account.address)
    assert account_container[address] == account


def test_contains(account, account_container, ecosystem):
    assert account.address in account_container

    # Ensure also works with int version of address
    address = ecosystem.encode_address(account.address)
    assert address in account_container
