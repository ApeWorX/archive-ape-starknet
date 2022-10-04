from typing import Iterator, Optional

from ape.api import ExplorerAPI, ReceiptAPI
from ape.types import AddressType
from ape.utils import raises_not_implemented
from ethpm_types import ContractType, HexBytes

from ape_starknet.accounts import BaseStarknetAccount
from ape_starknet.utils import pad_hex_str
from ape_starknet.utils.basemodel import StarknetBase


class StarknetExplorer(ExplorerAPI, StarknetBase):
    BASE_URIS = {
        "testnet": "https://goerli.voyager.online",
        "mainnet": "https://voyager.online",
    }

    @property
    def base_uri(self) -> str:
        network_name = self.provider.network.name
        return self.BASE_URIS.get(network_name, "")

    def get_address_url(self, address: AddressType) -> str:
        base_uri = self.base_uri
        return f"{base_uri}/contracts/{address}" if base_uri else ""

    def get_transaction_url(self, transaction_hash: str) -> str:
        base_uri = self.base_uri
        return f"{base_uri}/txns/{transaction_hash}" if base_uri else ""

    def get_contract_type(self, address: AddressType) -> Optional[ContractType]:
        if self.tokens.is_token(address):
            return self.tokens.contract_type

        elif address in self.account_contracts:
            starknet_account = self.account_contracts[address]
            assert isinstance(starknet_account, BaseStarknetAccount)  # for mypy
            return starknet_account.get_account_contract_type()

        code_and_abi = self.provider.get_code_and_abi(address)

        # Convert list of ints to bytes
        bytecode_str_list = [HexBytes(x).hex() for x in code_and_abi.bytecode]
        longest_str = len(max(bytecode_str_list, key=len)) - 2
        code_parts = [
            pad_hex_str(x, to_length=longest_str).replace("0x", "") for x in bytecode_str_list
        ]

        contract_type_dict = {
            "abi": code_and_abi.abi,
            "deploymentBytecode": {"bytecode": f"0x{''.join(code_parts)}"},
        }

        if "__execute__" in [a["name"] for a in code_and_abi.abi]:
            contract_type_dict["contractName"] = "Account"

        return ContractType.parse_obj(contract_type_dict)

    @raises_not_implemented
    def get_account_transactions(self, address: AddressType) -> Iterator[ReceiptAPI]:
        # TODO
        pass

    @raises_not_implemented
    def publish_contract(self, address: AddressType):
        # TODO
        pass
