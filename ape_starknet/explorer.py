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
        def _get_contract_type(address: AddressType) -> ContractType:
            if address not in self.cached_code:
                self.cached_code[address] = self.provider.get_code_and_abi(address)

            code = self.cached_code[address]
            return ContractType.parse_obj(code)

        original_address = address
        depth = 16
        index = 0
        final_contract_found = False
        checked_addresses = []

        while index < depth and not final_contract_found:
            contract_type = _get_contract_type(address)

            # Temporarily cache contract type at address so we can properly make contract calls
            self.chain_manager.contracts._local_contracts[address] = contract_type
            proxy_info = self.starknet._get_proxy_info(address, contract_type)

            if not proxy_info:
                final_contract_found = True
                break
            else:
                del self.chain_manager.contracts._local_contracts[address]
                checked_addresses.append(address)
                address = proxy_info.target
                if address in checked_addresses:
                    raise ValueError("Proxy cycical reference detected.")

                index += 1
                if index == 16:
                    raise ValueError(f"Too deep of search to find non-proxy contract type ({index}).")

        self.chain_manager.contracts[original_address] = contract_type
        return contract_type

    def get_account_transactions(self, address: AddressType) -> Iterator[ReceiptAPI]:
        # TODO
        yield from ()
