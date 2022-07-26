import pytest
from hexbytes import HexBytes

from ape_starknet.utils import get_random_private_key, is_checksum_address, to_checksum_address


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
