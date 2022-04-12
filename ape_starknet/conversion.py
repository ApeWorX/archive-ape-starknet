from typing import Any

from ape.api import ConverterAPI
from ape.types import AddressType
from eth_utils import is_checksum_address

from ape_starknet._utils import is_hex_address, to_checksum_address


# NOTE: This utility converter ensures that all bytes args can accept hex too
class StarknetAddressConverter(ConverterAPI):
    """
    A converter that converts ``str`` to ``AddressType``.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, str) and is_hex_address(value) and not is_checksum_address(value)

    def convert(self, value: str) -> AddressType:
        """
        Convert the given value to a ``AddressType``.

        Args:
            value (str): The address ``str`` to convert.

        Returns:
            ``AddressType``
        """

        return to_checksum_address(value)
