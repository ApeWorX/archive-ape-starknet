import os
from typing import Any, Dict, Iterator, List, Optional, Union
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

import requests
from ape.api import BlockAPI, ProviderAPI, ReceiptAPI, SubprocessProvider, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractInstance
from ape.exceptions import ProviderNotConnectedError, TransactionError, VirtualMachineError
from ape.types import AddressType, BlockID, ContractLog
from ape.utils import DEFAULT_NUMBER_OF_TEST_ACCOUNTS, cached_property
from ethpm_types import ContractType
from ethpm_types.abi import EventABI
from starknet_py.net import Client as StarknetClient
from starknet_py.net.models import parse_address
from starkware.starknet.definitions.transaction_type import TransactionType
from starkware.starknet.services.api.feeder_gateway.response_objects import (
    DeclareSpecificInfo,
    DeploySpecificInfo,
    InvokeSpecificInfo,
    StarknetBlock,
)
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
    client: Optional[StarknetClient] = None
    token_manager: TokenManager = TokenManager()
    default_gas_cost: int = 0
    cached_code: Dict[int, Dict] = {}

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
            self.client = StarknetClient(self.uri, chain=self.chain_id)

        return was_successful

    @property
    def starknet_client(self) -> StarknetClient:
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

        self.client = StarknetClient(self.uri, chain=self.chain_id)

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
    def get_code(self, address: str) -> bytes:
        # NOTE: Always return truthy value for code so that ape core works properly
        return self.get_code_and_abi(address).get("bytecode", b"PROXY")

    @handle_client_errors
    def get_abi(self, address: str) -> List[Dict]:
        return self.get_code_and_abi(address)["abi"]

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
    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        if self.network.name == LOCAL_NETWORK_NAME:
            return self.default_gas_cost

        if not isinstance(txn, StarknetTransaction):
            raise StarknetEcosystemError(
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
        elif block_id in ("pending", "latest"):
            kwarg = "block_number"
        elif isinstance(block_id, int):
            kwarg = "block_number"
            if block_id < 0:
                latest_block_number = self.get_block("latest").number
                block_id_int = latest_block_number + block_id + 1
                if block_id_int < 0:
                    raise ValueError(
                        f"Negative block number '{block_id_int}' results in non-existent block."
                    )

                block_id = block_id_int

        else:
            raise ValueError(f"Unsupported BlockID type '{type(block_id)}'.")

        block = self.starknet_client.get_block_sync(**{kwarg: block_id})
        return self.starknet.decode_block(block.dump())

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
    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        self.starknet_client.wait_for_tx_sync(txn_hash)
        txn_info = self.starknet_client.get_transaction_sync(tx_hash=txn_hash).transaction
        receipt = self.starknet_client.get_transaction_receipt_sync(
            tx_hash=txn_info.transaction_hash
        )
        receipt_dict: Dict[str, Any] = {"provider": self, **vars(receipt)}
        receipt_dict = get_dict_from_tx_info(txn_info, **receipt_dict)
        return self.starknet.decode_receipt(receipt_dict)

    def get_transactions_by_block(self, block_id: BlockID) -> Iterator[TransactionAPI]:
        block = self._get_block(block_id)
        for txn_info in block.transactions:
            txn_dict = get_dict_from_tx_info(txn_info)
            yield self.starknet.create_transaction(**txn_dict)

    @handle_client_errors
    def send_transaction(self, txn: TransactionAPI, token: Optional[str] = None) -> ReceiptAPI:
        txn_info = self._send_transaction(txn, token=token)
        invoking = txn.type == TransactionType.INVOKE_FUNCTION

        if "code" in txn_info and txn_info["code"] != StarkErrorCode.TRANSACTION_RECEIVED.name:
            raise TransactionError(message="Transaction not received.")

        error = txn_info.get("error", {})
        if error:
            message = error.get("message", error)
            raise StarknetProviderError(message)

        txn_hash = txn_info["transaction_hash"]
        receipt = self.get_transaction(txn_hash)

        if invoking and isinstance(txn, InvokeFunctionTransaction):
            returndata = txn_info.get("result", [])
            receipt.returndata = returndata.copy()

            if txn.original_method_abi:
                # Use ABI before going through account contract
                abi = txn.original_method_abi
                return_data = returndata[1:]
            else:
                abi = txn.method_abi
                return_data = returndata

            return_value = self.starknet.decode_returndata(abi, return_data)
            receipt.return_value = return_value

        return receipt

    @handle_client_errors
    def _send_transaction(
        self, txn: TransactionAPI, token: Optional[str] = None
    ) -> Union[DeclareSpecificInfo, DeploySpecificInfo, InvokeSpecificInfo]:
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
        return self.starknet_client.add_transaction_sync(starknet_txn, token=token)

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
        if txn.type == TransactionType.INVOKE_FUNCTION and not txn.max_fee:
            txn.max_fee = self.estimate_gas_cost(txn)

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

    def get_virtual_machine_error(self, exception: Exception) -> VirtualMachineError:
        return get_virtual_machine_error(exception) or VirtualMachineError(base_err=exception)

    def get_code_and_abi(self, address: Union[str, AddressType, int]):
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
