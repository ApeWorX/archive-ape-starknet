from typing import Dict, Optional, Union

from ape.api import Address
from ape.contracts import ContractInstance
from ape.exceptions import ContractError
from ape.types import AddressType
from starknet_devnet.fee_token import FeeToken  # type: ignore

from ape_starknet.utils import convert_contract_class_to_contract_type
from ape_starknet.utils.basemodel import StarknetBase


def missing_contract_error(token: str, contract_address: AddressType) -> ContractError:
    return ContractError(f"Incorrect '{token}' contract address '{contract_address}'.")


class TokenManager(StarknetBase):
    # The 'test_token' refers to the token that comes with Argent-X
    additional_tokens: Dict = {}

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

    def add_token(self, name: str, network: str, address: AddressType):
        if name not in self.additional_tokens:
            self.additional_tokens[name] = {}

        self.additional_tokens[name][network] = address

    def get_balance(self, account: Union[Address, AddressType], token: str = "eth") -> int:
        if hasattr(account, "address"):
            account = account.address  # type: ignore

        contract_address = self._get_contract_address(token=token)
        if not contract_address:
            return 0

        contract = self._get_contract(contract_address)
        return contract.balanceOf(account)[0]

    def transfer(
        self,
        sender: Union[int, AddressType],
        receiver: Union[int, AddressType],
        amount: int,
        token: str = "eth",
    ):
        if not isinstance(sender, int):
            sender = self.starknet.encode_address(sender)

        if not isinstance(receiver, int):
            receiver = self.starknet.encode_address(receiver)

        contract_address = self._get_contract_address(token=token)
        if not contract_address:
            return

        contract = self._get_contract(contract_address)
        sender_account = self.account_contracts[sender]
        return contract.transfer(receiver, amount, sender=sender_account)

    def _get_contract_address(self, token: str = "eth") -> Optional[AddressType]:
        network = self.provider.network.name
        return AddressType(self.token_address_map[token.lower()].get(network))  # type: ignore

    def _get_contract(self, address: AddressType) -> ContractInstance:
        # TODO: can remove proxy check once bug in ape regarding cached local
        #  proxies is resolved
        proxy_info = self.starknet.get_proxy_info(address)
        if proxy_info:
            contract_type = self.chain_manager.contracts[proxy_info.target]
            return ContractInstance(proxy_info.target, contract_type)

        else:
            contract = self.chain_manager.contracts.instance_at(address)
            if not isinstance(contract, ContractInstance):
                raise ValueError(f"Contract not found at address '{address}'.")

            return contract
