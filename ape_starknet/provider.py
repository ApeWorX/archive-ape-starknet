from typing import Any, Dict, Iterator, List, Optional, Union
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

from ape.api import BlockAPI, ProviderAPI, ReceiptAPI, SubprocessProvider, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.exceptions import ProviderError, ProviderNotConnectedError
from ape.types import AddressType, BlockID, ContractLog
from ape.utils import cached_property
from ethpm_types.abi import EventABI
from starknet_py.net import Client as StarknetClient  # type: ignore
from starknet_py.net.models import parse_address  # type: ignore
from starkware.starknet.definitions.transaction_type import TransactionType  # type: ignore
from starkware.starknet.services.api.feeder_gateway.response_objects import (  # type: ignore
    DeploySpecificInfo,
    InvokeSpecificInfo,
)

from ape_starknet._utils import PLUGIN_NAME, get_chain_id, handle_client_errors
from ape_starknet.config import StarknetConfig
from ape_starknet.transactions import InvokeFunctionTransaction, StarknetTransaction

DEFAULT_PORT = 8545


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
        return get_chain_id(self.network.name).value

    def get_balance(self, address: str) -> int:
        # TODO
        return 0

    @handle_client_errors
    def get_code(self, address: str) -> bytes:
        address_int = parse_address(address)
        code = self.starknet_client.get_code_sync(address_int)["bytecode"]  # type: ignore
        return code

    @handle_client_errors
    def get_nonce(self, address: str) -> int:
        # TODO: is this possible? usually the contract manages the nonce.
        return 0

    @handle_client_errors
    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        if not isinstance(txn, StarknetTransaction):
            raise ProviderError(
                "Unable to estimate the gas cost for a non-Starknet transaction "
                "using Starknet provider."
            )

        starknet_object = txn.as_starknet_object()

        if not self.client:
            raise ProviderNotConnectedError()

        return self.client.estimate_fee_sync(starknet_object)

    @property
    def gas_price(self) -> int:
        """
        **NOTE**: Currently, the gas price is fixed to always be 100 gwei.
        """
        return self.conversion_manager.convert("100 gwei", int)

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

    @handle_client_errors
    def send_call(self, txn: TransactionAPI) -> bytes:
        if not isinstance(txn, InvokeFunctionTransaction):
            type_str = f"{txn.type!r}" if isinstance(txn.type, bytes) else str(txn.type)
            raise ProviderError(
                f"Transaction must be from an invocation. Received type {type_str}."
            )

        if not self.client:
            raise ProviderNotConnectedError()

        return self.client.call_contract_sync(txn.as_starknet_object())

    @handle_client_errors
    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        self.starknet_client.wait_for_tx_sync(txn_hash)
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

    @handle_client_errors
    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        txn = self.prepare_transaction(txn)
        if not isinstance(txn, StarknetTransaction):
            raise ProviderError(
                "Unable to send non-Starknet transaction using a Starknet provider."
            )

        if txn.sender:
            # If using a sender, send the transaction from your sender's account contract.
            result = self.account_manager[txn.sender].send_transaction(txn)

        else:
            result = self.starknet_client.add_transaction_sync(txn.as_starknet_object())

        txn_hash = result["transaction_hash"]
        return self.get_transaction(txn_hash)

    @handle_client_errors
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

    @handle_client_errors
    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        if txn.type == TransactionType.INVOKE_FUNCTION and txn.max_fee is None:
            txn.max_fee = self.estimate_gas_cost(txn)

        return txn


__all__ = ["StarknetProvider"]
