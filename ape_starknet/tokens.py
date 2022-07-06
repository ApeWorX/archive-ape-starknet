from typing import TYPE_CHECKING, Dict, Optional, Union

from ape.api import Address
from ape.contracts import ContractInstance
from ape.exceptions import ContractError
from ape.types import AddressType
from starknet_devnet.fee_token import FeeToken

from eth_typing import HexAddress, HexStr
from ape_starknet.ecosystems import StarknetProxy
from ape_starknet.utils import convert_contract_class_to_contract_type, from_uint
from ape_starknet.utils.basemodel import StarknetBase

if TYPE_CHECKING:
    from ape_starknet.accounts import BaseStarknetAccount


def missing_contract_error(token: str, contract_address: AddressType) -> ContractError:
    return ContractError(f"Incorrect '{token}' contract address '{contract_address}'.")


class TokenManager(StarknetBase):
    # The 'test_token' refers to the token that comes with Argent-X
    additional_tokens: Dict = {}

    # NOTE: Can be deleted once ape can correctly cache local proxy deploys
    token_proxy_infos: Dict[AddressType, Optional[StarknetProxy]] = {}

    @property
    def token_address_map(self) -> Dict:
        local_eth = self.starknet.decode_address(FeeToken.ADDRESS)
        local_contract_type = convert_contract_class_to_contract_type(FeeToken.get_contract_class())
        self.chain_manager.contracts[local_eth] = local_contract_type

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
        contract_address = AddressType(HexAddress(HexStr(self.token_address_map[token.lower()].get(network))))
        if not contract_address:
            raise IndexError(f"No token '{token}'.")

        instance = self.chain_manager.contracts.instance_at(contract_address)
        if not isinstance(instance, ContractInstance):
            raise IndexError(f"No contract at address '{contract_address}'.")

        return instance

    def add_token(self, name: str, network: str, address: AddressType):
        if name not in self.additional_tokens:
            self.additional_tokens[name] = {}

        self.additional_tokens[name][network] = address

    def get_balance(self, account: Union[Address, AddressType], token: str = "eth") -> int:
        if hasattr(account, "address"):
            account = account.address  # type: ignore

        return from_uint(self[token].balanceOf(account))

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
            raise TypeError(
                f"Unhandled type for receiver '{receiver}'. Expects int, str, or account."
            )

        sender_account = self.account_contracts[sender] if isinstance(sender, (int, str)) else sender
        return self[token].transfer(receiver_address, amount, sender=sender_account)
