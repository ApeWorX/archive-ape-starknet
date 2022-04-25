from typing import TYPE_CHECKING, Dict, List, Optional

from ape.exceptions import ContractError, ProviderError
from ape.types import AddressType
from ape.utils import ManagerAccessMixin
from ethpm_types.abi import MethodABI

if TYPE_CHECKING:
    from ape_starknet.provider import StarknetProvider


def _select_method_abi(name: str, abi: List[Dict]) -> Optional[Dict]:
    for sub_abi in abi:
        if sub_abi["type"] == "constructor" and name == "constructor":
            return sub_abi

        elif sub_abi.get("name") == name:
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
        contract_address = self._get_contract_address(token=token)
        if not contract_address:
            return 0

        contract = self.provider.contract_at(contract_address)
        if "balanceOf" in [m.name for m in contract._contract_type.view_methods]:
            return contract.balanceOf(account)[0]

        # Handle proxy-implementation (not yet supported in ape-core)
        abi_name = "balanceOf"
        method_abi = self._get_method_abi(abi_name)
        if not method_abi:
            raise ContractError(f"Contract has no method '{abi_name}'.")

        ecosystem = self.provider.network.ecosystem
        method_abi_obj = MethodABI.parse_obj(method_abi)
        transaction = ecosystem.encode_transaction(contract_address, method_abi_obj, account)
        call_data = self.provider.send_call(transaction)
        return call_data[0]

    def transfer(self, sender: int, receiver: int, amount: int, token: str = "eth"):
        contract_address = self._get_contract_address(token=token)
        if not contract_address:
            return

        contract = self.provider.contract_at(contract_address)
        sender_address = self.provider.network.ecosystem.decode_address(sender)
        if "transfer" in [m.name for m in contract._contract_type.mutable_methods]:
            return contract.transfer(receiver, amount, sender=sender_address)

        # Handle proxy-implementation (not yet supported in ape-core)
        abi_name = "transfer"
        method_abi = self._get_method_abi(abi_name, token=token)
        if not method_abi:
            raise ContractError(f"Contract has no method named '{abi_name}'.")

        method_abi_obj = MethodABI.parse_obj(method_abi)
        transaction = self.provider.network.ecosystem.encode_transaction(
            contract_address, method_abi_obj, receiver, amount
        )
        account = self.account_manager.containers["starknet"][sender_address]  # type: ignore
        return account.send_transaction(transaction)  # type: ignore

    def _get_contract_address(self, token: str = "eth") -> Optional[AddressType]:
        network = self.provider.network.name
        return AddressType(self.TOKEN_ADDRESS_MAP[token.lower()].get(network))  # type: ignore

    def _get_method_abi(self, method_name: str, token: str = "eth") -> Optional[Dict]:
        contract_address = self._get_contract_address(token=token)
        if not contract_address:
            return None

        abi = self.provider.get_abi(contract_address)
        implementation_abi = _select_method_abi("implementation", abi)
        if not implementation_abi:
            raise ValueError(f"No method found with name '{method_name}'.")

        method_abi = MethodABI.parse_obj(implementation_abi)
        ecosystem = self.provider.network.ecosystem
        transaction = ecosystem.encode_transaction(contract_address, method_abi)
        return_data = self.provider.send_call(transaction)
        actual_contract_address_int = self.provider.network.ecosystem.decode_returndata(
            method_abi, return_data
        )
        actual_contract_address = self.provider.network.ecosystem.decode_address(
            actual_contract_address_int
        )
        actual_abi = self.provider.get_abi(actual_contract_address)
        selected_abi = _select_method_abi(method_name, actual_abi)
        return selected_abi
