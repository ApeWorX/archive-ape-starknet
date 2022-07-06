from typing import Iterator, Optional

from ape.api import ExplorerAPI, ReceiptAPI
from ape.types import AddressType
from ethpm_types import ContractType

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
        code = self.provider.get_code_and_abi(address)
        contract_type = ContractType.parse_obj(code)
        proxy_info = self.starknet._get_proxy_info(address, contract_type)
        if proxy_info:
            print("HERE")
            contract_type = self.get_contract_type(proxy_info.target)
            self.chain_manager.contracts[proxy_info.target] = contract_type
            self.chain_manager.contracts._local_proxies[address] = proxy_info
            if self.provider.network.name != LOCAL_NETWORK_NAME:
                self.chain_manager.contracts._cache_proxy_info_to_disk(address, proxy_info)

        else:
            self.chain_manager.contracts[address] = contract_type

        return contract_type

    def get_account_transactions(self, address: AddressType) -> Iterator[ReceiptAPI]:
        # TODO
        yield from ()
