from typing import Any

from ape.api import ConverterAPI
from ape.types import AddressType
from eth_typing import HexAddress, HexStr

from ape_starknet.accounts import BaseStarknetAccount
from ape_starknet.utils import PLUGIN_NAME, is_checksum_address, is_hex_address, to_checksum_address


# NOTE: This utility converter ensures that all bytes args can accept hex too
class StarknetAddressConverter(ConverterAPI):
    """
    A converter that converts ``str`` to ``AddressType``.
    """

    def is_convertible(self, value: Any) -> bool:
        provider = self.network_manager.active_provider
        return (provider is not None and provider.network.ecosystem.name == PLUGIN_NAME) and (
            (isinstance(value, str) and is_hex_address(value)) or isinstance(value, int)
        )

    def convert(self, value: str) -> AddressType:
        """
        Convert the given value to a ``AddressType``.

        Args:
            value (str): The address ``str`` to convert.

        Returns:
            ``AddressType``
        """

        if is_checksum_address(value):
            return AddressType(HexAddress(HexStr(value)))

        return to_checksum_address(value)


class StarknetAccountConverter(ConverterAPI):
    """
    A converter that converts accounts to address integers.
    """

    def is_convertible(self, value: Any) -> bool:
        return isinstance(value, BaseStarknetAccount)

    def convert(self, value: BaseStarknetAccount) -> int:
        return value.address_int
