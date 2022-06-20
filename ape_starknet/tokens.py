from typing import TYPE_CHECKING, Dict, Union

from ape.api import Address
from ape.contracts import ContractInstance
from ape.exceptions import ContractError
from ape.types import AddressType
from eth_typing import HexAddress, HexStr
from ethpm_types import ContractType
from starknet_devnet.fee_token import FeeToken

from ape_starknet.exceptions import StarknetProviderError
from ape_starknet.utils.basemodel import StarknetBase

if TYPE_CHECKING:
    from ape_starknet.accounts import BaseStarknetAccount


def missing_contract_error(token: str, contract_address: AddressType) -> ContractError:
    return ContractError(f"Incorrect '{token}' contract address '{contract_address}'.")


ERC20 = ContractType(
    **{
        "contractName": "ERC20",
        "abi": [
            {
                "type": "struct",
                "name": "Uint256",
                "members": [
                    {"name": "low", "type": "felt", "offset": 0},
                    {"name": "high", "type": "felt", "offset": 1},
                ],
                "size": 2,
            },
            {
                "type": "event",
                "name": "Transfer",
                "inputs": [
                    {"name": "from_", "type": "felt", "indexed": False},
                    {"name": "to", "type": "felt", "indexed": False},
                    {"name": "value", "type": "Uint256", "indexed": False},
                ],
                "anonymous": False,
            },
            {
                "type": "event",
                "name": "Approval",
                "inputs": [
                    {"name": "owner", "type": "felt", "indexed": False},
                    {"name": "spender", "type": "felt", "indexed": False},
                    {"name": "value", "type": "Uint256", "indexed": False},
                ],
                "anonymous": False,
            },
            {
                "type": "constructor",
                "stateMutability": "nonpayable",
                "inputs": [
                    {"name": "name", "type": "felt"},
                    {"name": "symbol", "type": "felt"},
                    {"name": "decimals", "type": "felt"},
                    {"name": "initial_supply", "type": "Uint256"},
                    {"name": "recipient", "type": "felt"},
                ],
            },
            {
                "type": "function",
                "name": "name",
                "stateMutability": "view",
                "inputs": [],
                "outputs": [{"name": "name", "type": "felt"}],
            },
            {
                "type": "function",
                "name": "symbol",
                "stateMutability": "view",
                "inputs": [],
                "outputs": [{"name": "symbol", "type": "felt"}],
            },
            {
                "type": "function",
                "name": "totalSupply",
                "stateMutability": "view",
                "inputs": [],
                "outputs": [{"name": "totalSupply", "type": "Uint256"}],
            },
            {
                "type": "function",
                "name": "decimals",
                "stateMutability": "view",
                "inputs": [],
                "outputs": [{"name": "decimals", "type": "felt"}],
            },
            {
                "type": "function",
                "name": "balanceOf",
                "stateMutability": "view",
                "inputs": [{"name": "account", "type": "felt"}],
                "outputs": [{"name": "balance", "type": "Uint256"}],
            },
            {
                "type": "function",
                "name": "allowance",
                "stateMutability": "view",
                "inputs": [{"name": "owner", "type": "felt"}, {"name": "spender", "type": "felt"}],
                "outputs": [{"name": "remaining", "type": "Uint256"}],
            },
            {
                "type": "function",
                "name": "transfer",
                "stateMutability": "nonpayable",
                "inputs": [
                    {"name": "recipient", "type": "felt"},
                    {"name": "amount", "type": "Uint256"},
                ],
                "outputs": [{"name": "success", "type": "felt"}],
            },
            {
                "type": "function",
                "name": "transferFrom",
                "stateMutability": "nonpayable",
                "inputs": [
                    {"name": "sender", "type": "felt"},
                    {"name": "recipient", "type": "felt"},
                    {"name": "amount", "type": "Uint256"},
                ],
                "outputs": [{"name": "success", "type": "felt"}],
            },
            {
                "type": "function",
                "name": "approve",
                "stateMutability": "nonpayable",
                "inputs": [
                    {"name": "spender", "type": "felt"},
                    {"name": "amount", "type": "Uint256"},
                ],
                "outputs": [{"name": "success", "type": "felt"}],
            },
            {
                "type": "function",
                "name": "increaseAllowance",
                "stateMutability": "nonpayable",
                "inputs": [
                    {"name": "spender", "type": "felt"},
                    {"name": "added_value", "type": "Uint256"},
                ],
                "outputs": [{"name": "success", "type": "felt"}],
            },
            {
                "type": "function",
                "name": "decreaseAllowance",
                "stateMutability": "nonpayable",
                "inputs": [
                    {"name": "spender", "type": "felt"},
                    {"name": "subtracted_value", "type": "Uint256"},
                ],
                "outputs": [{"name": "success", "type": "felt"}],
            },
        ],
    }
)


class TokenManager(StarknetBase):
    # The 'test_token' refers to the token that comes with Argent-X
    additional_tokens: Dict = {}
    contract_type = ERC20

    @property
    def token_address_map(self) -> Dict:
        local_eth = self.starknet.decode_address(FeeToken.ADDRESS)
        mainnet_eth = self.starknet.decode_address(
            "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7"
        )
        testnet_eth = self.starknet.decode_address(
            "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7"
        )
        testnet_test_token = self.starknet.decode_address(
            "0x07394cbe418daa16e42b87ba67372d4ab4a5df0b05c6e554d158458ce245bc10"
        )
        mainnet_test_token = self.starknet.decode_address(
            "0x07394cbe418daa16e42b87ba67372d4ab4a5df0b05c6e554d158458ce245bc10"
        )

        return {
            "eth": {"local": local_eth, "mainnet": mainnet_eth, "testnet": testnet_eth},
            "test_token": {"testnet": testnet_test_token, "mainnet": mainnet_test_token},
            **self.additional_tokens,
        }

    def __getitem__(self, token: str) -> ContractInstance:
        network = self.provider.network.name
        contract_address = AddressType(
            HexAddress(HexStr(self.token_address_map[token.lower()].get(network)))
        )
        if not contract_address:
            raise IndexError(f"No token '{token}'.")

        return ContractInstance(contract_address, ERC20)

    def is_token(self, address: AddressType) -> bool:
        network = self.provider.network.name
        return any(address == networks.get(network) for networks in self.token_address_map.values())

    def add_token(self, name: str, network: str, address: AddressType):
        if name not in self.additional_tokens:
            self.additional_tokens[name] = {}

        self.additional_tokens[name][network] = address

    def get_balance(self, account: Union[Address, AddressType], token: str = "eth") -> int:
        if hasattr(account, "address"):
            account = account.address  # type: ignore

        return self[token].balanceOf(account)

    def transfer(
        self,
        sender: Union[int, AddressType, "BaseStarknetAccount"],
        receiver: Union[int, AddressType, "BaseStarknetAccount"],
        amount: int,
        token: str = "eth",
    ):
        if isinstance(receiver, int):
            receiver_address = receiver
        elif hasattr(receiver, "address_int"):
            receiver_address = receiver.address_int  # type: ignore
        elif isinstance(receiver, str):
            receiver_address = self.starknet.encode_address(receiver)
        else:
            raise StarknetProviderError(
                f"Unhandled type for receiver '{receiver}'. Expects int, str, or account."
            )

        sender_account = (
            self.account_contracts[sender] if isinstance(sender, (int, str)) else sender
        )
        return self[token].transfer(receiver_address, amount, sender=sender_account)
