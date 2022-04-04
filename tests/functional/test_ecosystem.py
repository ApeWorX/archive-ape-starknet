import pytest
from ape.types import AddressType
from eth_typing import HexAddress, HexStr
from hexbytes import HexBytes

INT_ADDRESS = 14543129564252315649550252856970912276603599239311963926081534426621736121411
STR_ADDRESS = "0x20271ea04cB854E105d948019Ba1FCdFa61d76D73539700Ff6DD456bcB7bF443"
HEXBYTES_ADDRESS = HexBytes(STR_ADDRESS)


@pytest.mark.parametrize("value", (INT_ADDRESS, STR_ADDRESS, HEXBYTES_ADDRESS))
def test_encode_and_decode_address(value, ecosystem):
    decoded_address = ecosystem.decode_address(value)
    expected = AddressType(HexAddress(HexStr(STR_ADDRESS)))
    assert decoded_address == expected

    # The values should _always_ encode back to the INT_ADDRESS.
    re_encoded_address = ecosystem.encode_address(decoded_address)
    assert re_encoded_address == INT_ADDRESS
