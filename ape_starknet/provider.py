from typing import Any, Dict, Iterator, List, Optional, Union
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

from ape.api import BlockAPI, ProviderAPI, ReceiptAPI, SubprocessProvider, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.exceptions import ProviderError
from ape.types import AddressType, BlockID, ContractLog
from ape.utils import cached_property
from ethpm_types.abi import EventABI
from starknet_py.net import Client as StarknetClient  # type: ignore
from starknet_py.net.client import BadRequest  # type: ignore
from starknet_py.net.models import parse_address  # type: ignore
from starkware.starknet.definitions.transaction_type import TransactionType  # type: ignore
from starkware.starknet.services.api.feeder_gateway.response_objects import (  # type: ignore
    DeploySpecificInfo,
    InvokeSpecificInfo,
)

from ape_starknet._utils import PLUGIN_NAME, get_chain_id
from ape_starknet.config import StarknetConfig
from ape_starknet.transactions import StarknetTransaction

DEFAULT_PORT = 8545


def handle_client_errors(f):
    def func(*args, **kwargs):
        try:
            f(*args, **kwargs)
        except BadRequest as err:
            # TODO: remove when I am sure anomolies are gone
            raise

            msg = err.text if hasattr(err, "text") else str(err)
            raise ProviderError(msg) from err

    return func


class StarknetProvider(SubprocessProvider, ProviderAPI):
    """
    A Starknet provider.
    """

    # Gets set when 'connect()' is called.
    client: Optional[StarknetClient] = None

    @property
    def process_name(self) -> str:
        return "starknet-devnet"

    @property
    def is_connected(self) -> bool:
        try:
            urlopen(self.uri)
            return True
        except HTTPError as err:
            return err.code == 404  # Task failed successfully
        except Exception:
            return False

    @property
    def starknet_client(self) -> StarknetClient:
        if not self.is_connected:
            raise ProviderError("Provider is not connected to Starknet.")

        return self.client

    def build_command(self) -> List[str]:
        parts = urlparse(self.uri)
        return ["starknet-devnet", "--host", str(parts.hostname), "--port", str(parts.port)]

    @cached_property
    def plugin_config(self) -> StarknetConfig:
        return self.config_manager.get_config(PLUGIN_NAME) or StarknetConfig()  # type: ignore

    @cached_property
    def uri(self) -> str:
        network_config = self.plugin_config.providers.dict().get(self.network.name)
        if not network_config:
            raise ProviderError(f"Unknown network '{self.network.name}'.")

        return network_config.get("uri") or f"http://127.0.0.1:{DEFAULT_PORT}"

    def connect(self):
        if self.network.name == LOCAL_NETWORK_NAME:
            # Behave like a 'SubprocessProvider'
            if not self.is_connected:
                super().connect()

            self.start()

        self.client = StarknetClient(self.uri, chain=self.chain_id)

    def disconnect(self):
        self.client = None
        super().disconnect()

    def update_settings(self, new_settings: dict):
        pass

    @property
    def chain_id(self) -> int:
        return get_chain_id(self.network.name)

    def get_balance(self, address: str) -> int:
        return 0

    @handle_client_errors
    def get_code(self, address: str) -> bytes:
        address_int = parse_address(address)
        return self.starknet_client.get_code_sync(address_int)["bytecode"]  # type: ignore

    def get_nonce(self, address: str) -> int:
        # TODO: is this possible? usually the contract manages the nonce.
        return 0

    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        # TODO
        return 0

    @property
    def gas_price(self) -> int:
        # TODO
        return 0

    @property
    def priority_fee(self) -> int:
        # TODO
        return 0

    @property
    def base_fee(self) -> int:
        # TODO
        return 0

    @handle_client_errors
    def get_block(self, block_id: BlockID) -> BlockAPI:
        if isinstance(block_id, (int, str)) and len(str(block_id)) == 76:
            kwarg = "block_hash"
        elif isinstance(block_id, int) or block_id == "pending":
            kwarg = "block_number"
        else:
            raise ValueError(f"Unsupported BlockID type '{type(block_id)}'.")

        block = self.starknet_client.get_block_sync(**{kwarg: block_id})
        return self.network.ecosystem.decode_block(block.dump())

    def send_call(self, txn: TransactionAPI) -> bytes:
        # TODO
        return b""

    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        try:
            self.starknet_client.wait_for_tx_sync(txn_hash)
        except Exception as err:
            raise
            raise ProviderError(str(err)) from err

        receipt = self.starknet_client.get_transaction_receipt_sync(tx_hash=txn_hash)
        receipt_dict: Dict[str, Any] = {"provider": self, **vars(receipt)}
        txn_info = self.starknet_client.get_transaction_sync(tx_hash=txn_hash).transaction

        if isinstance(txn_info, DeploySpecificInfo):
            txn_type = TransactionType.DEPLOY
        elif isinstance(txn_info, InvokeSpecificInfo):
            txn_type = TransactionType.INVOKE_FUNCTION
        else:
            raise ValueError(f"No value found for '{txn_info}'.")

        ecosytem = self.provider.network.ecosystem
        receipt_dict["contract_address"] = ecosytem.decode_address(txn_info.contract_address)
        receipt_dict["type"] = txn_type
        return self.network.ecosystem.decode_receipt(receipt_dict)

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        if not isinstance(txn, StarknetTransaction):
            raise ProviderError("Unable to send non-Starknet transaction using Starknet provider.")

        starknet_txn = txn.as_starknet_object()
        result = self.starknet_client.add_transaction_sync(starknet_txn)

        if result.get("error"):
            message = result["error"].get("message") or "Transaction failed"
            raise ProviderError(message)

        txn_hash = result["transaction_hash"]
        return self.get_transaction(txn_hash)

    def get_contract_logs(
        self,
        address: Union[AddressType, List[AddressType]],
        abi: Union[EventABI, List[EventABI]],
        start_block: Optional[int] = None,
        stop_block: Optional[int] = None,
        block_page_size: Optional[int] = None,
        event_parameters: Optional[Dict] = None,
    ) -> Iterator[ContractLog]:
        raise NotImplementedError("TODO")

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        # TODO: Handle fees
        return txn


__all__ = ["StarknetProvider"]
