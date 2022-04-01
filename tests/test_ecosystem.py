from ape.types import AddressType
from eth_typing import HexAddress, HexStr

INT_ADDRESS = 1454312956425231564955025285697091227660359923931196392608153442662173612141


def test_encode_and_decode_address(ecosystem):
    decoded_address = ecosystem.decode_address(INT_ADDRESS)
    assert decoded_address == AddressType(
        HexAddress(HexStr("0x3371cA9a145A2168095bA668F9032E32A36257bEbb8f19B324953BdfAbF986D"))
    )
    re_encoded_address = ecosystem.encode_address(decoded_address)
    assert re_encoded_address == INT_ADDRESS
