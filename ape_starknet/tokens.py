from typing import TYPE_CHECKING, Dict, List, Optional

from ape.exceptions import ProviderError
from ape.types import AddressType
from ape.utils import ManagerAccessMixin
from eth_typing import HexAddress, HexStr
from ethpm_types.abi import MethodABI

if TYPE_CHECKING:
    from ape_starknet.provider import StarknetProvider


def _select_method_abi(name: str, abi: List[Dict]) -> Optional[Dict]:
    for sub_abi in abi:
        if sub_abi["type"] == "constructor" and name == "constructor":
            return sub_abi

        elif hasattr(sub_abi, "name") and sub_abi["name"] == name:
            return sub_abi

    return None


class TokenManager(ManagerAccessMixin):
    TOKEN_ADDRESS_MAP = {
        "eth": {
            "testnet": "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7",
        },
        "test_token": {
            "testnet": "0x07394cbe418daa16e42b87ba67372d4ab4a5df0b05c6e554d158458ce245bc10",
            "mainnet": "0x06a09ccb1caaecf3d9683efe335a667b2169a409d19c589ba1eb771cd210af75",
        },
    }

    @property
    def provider(self) -> "StarknetProvider":
        from ape_starknet.provider import StarknetProvider

        provider = super().provider
        if not isinstance(provider, StarknetProvider):
            raise ProviderError("Must be using a Starknet provider.")

        return provider

    def get_balance(self, account: AddressType, token: str = "eth") -> int:
        token_contract_address = self._get_contract_address(token=token)
        method_abi = self._get_method_abi("balanceOf")
        ecosystem = self.provider.network.ecosystem
        method_abi = MethodABI.parse_obj(method_abi)
        transaction = ecosystem.encode_transaction(token_contract_address, method_abi, account)
        return_data = self.provider.send_call(transaction)
        result = ecosystem.decode_return_data(method_abi, return_data)
        return result[0]

    def transfer(self, sender: int, receiver: int, amount: int, token: str = "eth"):
        contract_address = self._get_contract_address(token=token)
        method_abi = self._get_method_abi("transfer", token=token)
        method_abi = MethodABI.parse_obj(method_abi)
        transaction = self.provider.network.ecosystem.encode_transaction(
            contract_address, method_abi, receiver, amount
        )
        return self.account_manager[sender].send_transaction(transaction)

    def _get_contract_address(self, token: str = "eth") -> AddressType:
        network = self.provider.network.name
        raw_address = HexAddress(HexStr(self.TOKEN_ADDRESS_MAP[token.lower()][network]))
        return AddressType(raw_address)

    def _get_method_abi(self, method_name: str, token: str = "eth"):
        contract_address = self._get_contract_address(token=token)
        abi = self.provider.get_abi(contract_address)
        selected_abi = _select_method_abi(method_name, abi)
        if not selected_abi:
            # Check if proxy
            implementation_abi = _select_method_abi("implementation", abi)
            method_abi = MethodABI.parse_obj(implementation_abi)
            ecosystem = self.provider.network.ecosystem
            transaction = ecosystem.encode_transaction(contract_address, method_abi)
            return_data = self.provider.send_call(transaction)
            result = ecosystem.decode_return_data(method_abi, return_data)
            actual_contract_address = result[0]
            actual_abi = self.provider.get_abi(actual_contract_address)
            selected_abi = _select_method_abi(method_name, actual_abi)

        if not selected_abi:
            raise ValueError(f"No method found with name '{method_name}'.")

        return selected_abi
