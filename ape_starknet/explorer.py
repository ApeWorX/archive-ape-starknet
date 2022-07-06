from typing import Dict, Iterator, Optional

from ape.api import ExplorerAPI, ReceiptAPI
from ape.types import AddressType
from ethpm_types import ContractType

from ape_starknet.utils.basemodel import StarknetBase


class StarknetExplorer(ExplorerAPI, StarknetBase):
    BASE_URIS = {
        "testnet": "https://goerli.voyager.online",
        "mainnet": "https://voyager.online",
    }

    cached_code: Dict[AddressType, Dict] = {}

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
        if address not in self.cached_code:
            self.cached_code[address] = self.provider.get_code_and_abi(address)

        code = self.cached_code[address]
        contract_type = ContractType.parse_obj(code)
        return contract_type

    def get_account_transactions(self, address: AddressType) -> Iterator[ReceiptAPI]:
        # TODO
        yield from ()
