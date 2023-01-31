from typing import TYPE_CHECKING, Dict, Union, cast

from ape.api import AccountAPI, Address
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractInstance
from ape.exceptions import ContractError
from ape.logging import logger
from ape.types import AddressType
from ape.utils import cached_property
from ethpm_types import ContractType
from starknet_devnet.fee_token import FeeToken
from starknet_py.constants import FEE_CONTRACT_ADDRESS

from ape_starknet.ecosystems import NETWORKS
from ape_starknet.exceptions import StarknetTokensError
from ape_starknet.utils import STARKNET_FEE_TOKEN_SYMBOL, to_int
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
TEST_TOKEN_ADDRESS = "0x07394cbe418daa16e42b87ba67372d4ab4a5df0b05c6e554d158458ce245bc10"


class TokenManager(StarknetBase):
    # The 'test_token' refers to the token that comes with Argent-X
    additional_tokens: Dict[str, Dict[str, int]] = {}
    contract_type = ERC20

    # Map of address int to symbols to balance.
    balance_cache: Dict[int, Dict[str, int]] = {}

    cache_enabled: Dict[str, bool] = {LOCAL_NETWORK_NAME: True, **{n: False for n in NETWORKS}}

    @property
    def token_address_map(self) -> Dict:
        return {
            **self._base_token_address_map,
            **self.additional_tokens,
        }

    @cached_property
    def _base_token_address_map(self) -> Dict[str, Dict[str, int]]:
        local_eth = FeeToken.ADDRESS
        live_eth = to_int(FEE_CONTRACT_ADDRESS)
        live_token = to_int(TEST_TOKEN_ADDRESS)

        if self.provider.network.name == LOCAL_NETWORK_NAME:
            self.chain_manager.contracts[
                self.starknet.decode_address(local_eth)
            ] = self.contract_type
        else:
            self.chain_manager.contracts[
                self.starknet.decode_address(live_eth)
            ] = self.contract_type

        return {
            "eth": {
                "local": local_eth,
                "testnet": live_eth,
                "testnet2": live_eth,
                "mainnet": live_eth,
            },
            "test_token": {"testnet": live_token, "testnet2": live_token, "mainnet": live_token},
        }

    def __getitem__(self, token: str) -> ContractInstance:
        network = self.provider.network.name
        token = token.lower()
        if token not in self.token_address_map or not self.token_address_map[token]:
            raise StarknetTokensError(f"Token '{token}' not found.")

        address = self.token_address_map[token].get(network)
        if not address:
            available_networks = ",".join(self.token_address_map[token])
            raise StarknetTokensError(
                f"Token '{token}' not deployed on network "
                f"'{network}' (available networks={available_networks})."
            )

        address_str = self.starknet.decode_address(address)
        return ContractInstance(address_str, ERC20)

    def is_token(self, address: Union[AddressType, int, Address]) -> bool:
        network = self.provider.network.name
        address_int = to_int(address)
        return any(
            address_int == networks.get(network) for networks in self.token_address_map.values()
        )

    def add_token(self, name: str, network: str, address: Union[AddressType, int]):
        if name in self.additional_tokens:
            self.additional_tokens[name][network] = to_int(address)
        else:
            self.additional_tokens[name] = {network: to_int(address)}

    def get_balance(
        self, account: Union[Address, AddressType], token: str = STARKNET_FEE_TOKEN_SYMBOL.lower()
    ) -> int:
        if hasattr(account, "address"):
            address = cast(Address, account).address
        else:
            address = cast(AddressType, account)

        address_int = to_int(address)
        network = self.provider.network.name
        if not self.cache_enabled.get(network, False):
            # Strictly use provider.
            balance = self.request_balance(address, token=token)
            self.balance_cache[address_int] = {token: balance}

        elif address_int not in self.balance_cache:
            balance = self.request_balance(address, token=token)
            self.balance_cache[address_int] = {token: balance}

        elif token not in self.balance_cache[address_int]:
            self.balance_cache[address_int][token] = self.request_balance(address, token=token)

        return self.balance_cache[address_int][token]

    def request_balance(
        self, account: Union[AddressType, int], token: str = STARKNET_FEE_TOKEN_SYMBOL.lower()
    ) -> int:
        """
        Get the balance from the provider and update the cache.
        """

        account_int = to_int(account)
        amount = self[token].balanceOf(account_int)
        amount_int = self._convert_amount_to_int(amount)

        # Update cache to save requests (only if caching enabled).
        if account_int in self.balance_cache:
            self.balance_cache[account_int][token] = amount_int
        else:
            self.balance_cache[account_int] = {token: amount_int}

        return amount_int

    def transfer(
        self,
        sender: Union[int, AddressType, "BaseStarknetAccount"],
        receiver: Union[int, AddressType, "BaseStarknetAccount"],
        amount: int,
        token: str = STARKNET_FEE_TOKEN_SYMBOL.lower(),
        **kwargs,
    ):
        receiver_int = to_int(receiver)
        sender_account = cast(
            "BaseStarknetAccount",
            (self.account_container[sender] if isinstance(sender, (int, str)) else sender),
        )
        result = self[token].transfer(receiver_int, amount, sender=sender_account, **kwargs)

        # NOTE: the fees paid by the sender get updated in `provider.send_transaction()`.
        amount_int = self._convert_amount_to_int(amount)
        self.update_cache(sender_account.address_int, -amount_int, token=token)
        self.update_cache(receiver_int, amount_int, token=token)
        return result

    def update_cache(
        self,
        address: Union[AccountAPI, AddressType, int],
        amount: Union[int, Dict],
        token: str = STARKNET_FEE_TOKEN_SYMBOL.lower(),
    ):
        amount_int = self._convert_amount_to_int(amount)
        address_int = to_int(address)
        if address_int not in self.balance_cache or token not in self.balance_cache[address_int]:
            # Set the balance from a request to the provider.
            self.request_balance(address_int, token=token)
            return

        current_balance: int = self.balance_cache[address_int][token]
        if current_balance + amount_int < 0:
            actual_balance = self.request_balance(address_int, token=token)
            logger.error(
                f"Balance cache corrupted - "
                f"attempted to set as {amount_int} when actual balance is {actual_balance}"
            )

        else:
            self.balance_cache[address_int][token] += amount_int

    def _convert_amount_to_int(self, amount: Union[int, Dict]) -> int:
        if isinstance(amount, int):
            return amount

        elif isinstance(amount, dict) and "low" in amount and "high" in amount:
            return (amount["high"] << 128) + amount["low"]

        elif isinstance(amount, dict) and "low" in amount:
            return amount["low"]

        elif isinstance(amount, (list, tuple)) and len(amount) == 2:
            return (amount[1] << 128) + amount[0]

        elif isinstance(amount, (list, tuple)) and len(amount) == 1:
            return amount[0]

        raise StarknetTokensError(f"Unable to handle transfer value '{amount}'.")


tokens = TokenManager()
