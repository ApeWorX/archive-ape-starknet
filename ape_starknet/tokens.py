from typing import TYPE_CHECKING

from ape.types import AddressType
from starknet_py.contract import Contract  # type: ignore

if TYPE_CHECKING:
    from ape_starknet.provider import StarknetProvider


class TokenManager:
    TOKEN_ADDRESS_MAP = {
        "eth": {
            "testnet": "0x07394cbe418daa16e42b87ba67372d4ab4a5df0b05c6e554d158458ce245bc10",
            "mainnet": "0x06a09ccb1caaecf3d9683efe335a667b2169a409d19c589ba1eb771cd210af75",
        }
    }

    def __init__(self, provider: "StarknetProvider"):
        self.provider = provider

    def get_balance(self, account: AddressType, token: str = "eth") -> int:
        network = self.provider.network
        network_name = network.name
        contract_address = self.TOKEN_ADDRESS_MAP[token][network_name]
        token_contract = Contract.from_address_sync(contract_address, self.provider.client)
        address_arg = network.ecosystem.encode_address(account)
        result = token_contract.functions["balanceOf"].call_sync(address_arg)
        return result.balance
