import os
from typing import Any, Dict, Iterator, List, Optional, Union
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

import requests
from ape.api import BlockAPI, ProviderAPI, ReceiptAPI, SubprocessProvider, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractInstance
from ape.exceptions import ProviderNotConnectedError, TransactionError
from ape.types import AddressType, BlockID, ContractLog, LogFilter
from ape.utils import DEFAULT_NUMBER_OF_TEST_ACCOUNTS, cached_property, raises_not_implemented
from ethpm_types import ContractType
from starknet_py.net.client_models import (
    BlockSingleTransactionTrace,
    ContractCode,
    InvokeTransaction,
    SentTransactionResponse,
    StarknetBlock,
)
from starknet_py.net.gateway_client import GatewayClient
from starknet_py.net.models import parse_address
from starkware.starkware_utils.error_handling import StarkErrorCode

from ape_starknet.config import DEFAULT_PORT, StarknetConfig
from ape_starknet.exceptions import StarknetEcosystemError, StarknetProviderError
from ape_starknet.tokens import TokenManager
from ape_starknet.transactions import (
    ContractDeclaration,
    InvokeFunctionTransaction,
    StarknetTransaction,
)
from ape_starknet.utils import (
    ALPHA_MAINNET_WL_DEPLOY_TOKEN_KEY,
    DEFAULT_ACCOUNT_SEED,
    PLUGIN_NAME,
    extract_trace_data,
    get_chain_id,
    get_dict_from_tx_info,
    get_virtual_machine_error,
    handle_client_errors,
)
from ape_starknet.utils.basemodel import StarknetBase


class StarknetProvider(SubprocessProvider, ProviderAPI, StarknetBase):
    """
    A Starknet provider.
    """

    # Gets set when 'connect()' is called.
    client: Optional[GatewayClient] = None
    token_manager: TokenManager = TokenManager()
    cached_code: Dict[int, ContractCode] = {}

    @property
    def process_name(self) -> str:
        return "starknet-devnet"

    @property
    def is_connected(self) -> bool:
        was_successful = False
        try:
            urlopen(self.uri)
            was_successful = True
        except HTTPError as err:
            was_successful = err.code == 404  # Task failed successfully
        except Exception:
            was_successful = False

        if was_successful and self.client is None:
            self.client = GatewayClient(self.uri, chain=self.chain_id)

        return was_successful

    @property
    def starknet_client(self) -> GatewayClient:
        if not self.is_connected:
            raise StarknetProviderError("Provider is not connected to Starknet.")

        return self.client

    def build_command(self) -> List[str]:
        parts = urlparse(self.uri)
        return [
            self.process_name,
            "--host",
            str(parts.hostname),
            "--port",
            str(parts.port),
            "--accounts",
            str(DEFAULT_NUMBER_OF_TEST_ACCOUNTS),
            "--seed",
            str(DEFAULT_ACCOUNT_SEED),
        ]

    @cached_property
    def plugin_config(self) -> StarknetConfig:
        return self.config_manager.get_config(PLUGIN_NAME) or StarknetConfig()  # type: ignore

    @cached_property
    def uri(self) -> str:
        network_config = self.plugin_config.provider.dict().get(self.network.name)
        if not network_config:
            raise StarknetProviderError(f"Unknown network '{self.network.name}'.")

        return network_config.get("uri") or f"http://127.0.0.1:{DEFAULT_PORT}"

    def connect(self):
        if self.network.name == LOCAL_NETWORK_NAME:
            # Behave like a 'SubprocessProvider'
            if not self.is_connected:
                super().connect()

            self.start()

        self.client = GatewayClient(self.uri, chain=self.chain_id)

    def disconnect(self):
        self.client = None
        super().disconnect()

    def update_settings(self, new_settings: dict):
        pass

    @property
    def chain_id(self) -> int:
        return get_chain_id(self.network.name).value

    @handle_client_errors
    def get_balance(self, address: AddressType) -> int:
        account = self.account_contracts[address]
        return self.token_manager.get_balance(account.address)

    @handle_client_errors
    def get_code(self, address: str) -> List[int]:
        # NOTE: Always return truthy value for code so that Ape core works properly
        return self.get_code_and_abi(address).bytecode or [ord(c) for c in "PROXY"]

    @handle_client_errors
    def get_abi(self, address: str) -> List[Dict]:
        return self.get_code_and_abi(address).abi

    @handle_client_errors
    def get_nonce(self, address: AddressType) -> int:
        # Check if passing a public-key address of a local account
        if address in self.account_contracts.public_key_addresses:
            contract_address = self.account_contracts.get_account(address).address
            if contract_address:
                address = contract_address

        checksum_address = self.starknet.decode_address(address)
        contract = self.chain_manager.contracts.instance_at(checksum_address)

        if not isinstance(contract, ContractInstance):
            raise StarknetProviderError(f"Account contract '{checksum_address}' not found.")

        return contract.get_nonce()

    @handle_client_errors
    def estimate_gas_cost(self, txn: StarknetTransaction) -> int:
        if not self.client:
            raise ProviderNotConnectedError()

        starknet_object = txn.as_starknet_object()
        estimated_fee = self.client.estimate_fee_sync(starknet_object)
        return estimated_fee.overall_fee

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
        elif block_id in ("pending", "latest"):
            kwarg = "block_number"
        elif isinstance(block_id, int):
            kwarg = "block_number"
            if block_id < 0:
                latest_block_number = self.get_block("latest").number
                block_id_int = latest_block_number + block_id + 1
                if block_id_int < 0:
                    raise StarknetProviderError(f"Block with number '{block_id_int}' not found.")

                block_id = block_id_int

        else:
            raise StarknetProviderError(f"Unsupported BlockID type '{type(block_id)}'.")

        block = self.starknet_client.get_block_sync(**{kwarg: block_id})
        return self.starknet.decode_block(block)

    def _get_block(self, block_id: BlockID) -> StarknetBlock:
        kwarg = (
            "block_hash"
            if isinstance(block_id, (int, str)) and len(str(block_id)) == 76
            else "block_number"
        )
        return self.starknet_client.get_block_sync(**{kwarg: block_id})

    @handle_client_errors
    def send_call(self, txn: TransactionAPI) -> bytes:
        if not isinstance(txn, InvokeFunctionTransaction):
            type_str = f"{txn.type!r}" if isinstance(txn.type, bytes) else str(txn.type)
            raise StarknetProviderError(
                f"Transaction must be from an invocation. Received type {type_str}."
            )

        if not self.client:
            raise ProviderNotConnectedError()

        starknet_obj = txn.as_starknet_object()
        return self.client.call_contract_sync(starknet_obj)  # type: ignore

    @handle_client_errors
    def _get_traces(self, block_number: int) -> List[BlockSingleTransactionTrace]:
        block_traces = self.starknet_client.get_block_traces_sync(block_number=block_number)
        return block_traces.traces

    @handle_client_errors
    def _get_single_trace(
        self, block_number: int, txn_hash: int
    ) -> Optional[BlockSingleTransactionTrace]:
        traces = self._get_traces(block_number)
        return next((trace for trace in traces if trace.transaction_hash == txn_hash), None)

    @handle_client_errors
    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        self.starknet_client.wait_for_tx_sync(txn_hash)
        txn_info = self.starknet_client.get_transaction_sync(tx_hash=txn_hash)
        receipt = self.starknet_client.get_transaction_receipt_sync(tx_hash=txn_hash)

        trace_data = {}
        if isinstance(txn_info, InvokeTransaction):
            trace = self._get_single_trace(receipt.block_number, receipt.hash)
            trace_data = extract_trace_data(trace)

        receipt_dict: Dict[str, Any] = {"provider": self, **trace_data, **vars(receipt)}
        receipt_dict = get_dict_from_tx_info(txn_info, **receipt_dict)
        return self.starknet.decode_receipt(receipt_dict)

    def get_transactions_by_block(self, block_id: BlockID) -> Iterator[TransactionAPI]:
        block = self._get_block(block_id)
        for txn_info in block.transactions:
            txn_dict = get_dict_from_tx_info(txn_info)
            yield self.starknet.create_transaction(**txn_dict)

    @handle_client_errors
    def send_transaction(self, txn: TransactionAPI, token: Optional[str] = None) -> ReceiptAPI:
        response = self._send_transaction(txn, token=token)
        if response.code != StarkErrorCode.TRANSACTION_RECEIVED.name:
            raise TransactionError(message="Transaction not received.")

        receipt = self.get_transaction(response.transaction_hash)

        if isinstance(txn, InvokeFunctionTransaction):
            if txn.original_method_abi:
                # Use ABI before going through account contract
                abi = txn.original_method_abi
            else:
                abi = txn.method_abi

            return_value = self.starknet.decode_returndata(abi, receipt.returndata)
            receipt.return_value = return_value

        return receipt

    def _send_transaction(
        self, txn: TransactionAPI, token: Optional[str] = None
    ) -> SentTransactionResponse:
        txn = self.prepare_transaction(txn)
        if not token and hasattr(txn, "token") and txn.token:  # type: ignore
            token = txn.token  # type: ignore
        else:
            token = os.environ.get(ALPHA_MAINNET_WL_DEPLOY_TOKEN_KEY)

        if not isinstance(txn, StarknetTransaction):
            raise StarknetEcosystemError(
                "Unable to send non-Starknet transaction using a Starknet provider."
            )

        starknet_txn = txn.as_starknet_object()
        return self.starknet_client.send_transaction_sync(starknet_txn, token=token)

    @raises_not_implemented
    def get_contract_logs(self, log_filter: LogFilter) -> Iterator[ContractLog]:
        pass

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        return txn

    def set_timestamp(self, new_timestamp: int):
        pending_timestamp = self.get_block("pending").timestamp
        seconds_to_increase = new_timestamp - pending_timestamp
        response = requests.post(
            url=f"{self.uri}/increase_time", json={"time": seconds_to_increase}
        )
        response.raise_for_status()
        response_data = response.json()
        if "timestamp_increased_by" not in response_data:
            raise StarknetProviderError(response_data)

    def get_virtual_machine_error(self, exception: Exception):
        return get_virtual_machine_error(exception)

    def get_code_and_abi(self, address: Union[str, AddressType, int]) -> ContractCode:
        address_int = parse_address(address)

        # Cache code for faster look-up
        if address_int not in self.cached_code:
            self.cached_code[address_int] = self.starknet_client.get_code_sync(address_int)

        return self.cached_code[address_int]

    @handle_client_errors
    def declare(self, contract_type: ContractType) -> ContractDeclaration:
        transaction = self.starknet.encode_contract_declaration(contract_type)
        return self.provider.send_transaction(transaction)


__all__ = ["StarknetProvider"]
