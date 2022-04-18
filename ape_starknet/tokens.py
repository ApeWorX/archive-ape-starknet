from typing import TYPE_CHECKING, Dict, List, Optional

from ape.exceptions import ProviderError
from ape.types import AddressType
from ape.utils import ManagerAccessMixin

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
        instance = self.provider.contract_at(contract_address)
        return instance.balanceOf(account.lower())[0]

    def transfer(self, sender: int, receiver: int, amount: int, token: str = "eth"):
        contract_address = self._get_contract_address(token=token)
        contract = self.provider.contract_at(contract_address)
        sender_account = self.account_manager[sender]
        return contract.transfer(receiver, amount, sender=sender_account)

    def _get_contract_address(self, token: str = "eth") -> AddressType:
        network = self.provider.network.name
        return AddressType(self.TOKEN_ADDRESS_MAP[token.lower()][network])
