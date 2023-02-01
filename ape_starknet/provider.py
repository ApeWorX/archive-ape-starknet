import os
from dataclasses import asdict
from typing import Any, Dict, Iterator, List, Optional, Union, cast
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

from ape.api import BlockAPI, ProviderAPI, ReceiptAPI, SubprocessProvider, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.exceptions import ProviderNotConnectedError, TransactionError, VirtualMachineError
from ape.logging import logger
from ape.types import AddressType, BlockID, ContractLog, LogFilter, RawAddress
from ape.utils import DEFAULT_NUMBER_OF_TEST_ACCOUNTS, cached_property, raises_not_implemented
from hexbytes import HexBytes
from requests import Session
from starknet_py.net.client_errors import ContractNotFoundError
from starknet_py.net.client_models import (
    BlockSingleTransactionTrace,
    ContractCode,
    SentTransactionResponse,
    StarknetBlock,
)
from starknet_py.net.gateway_client import GatewayClient
from starknet_py.net.models import parse_address
from starkware.starkware_utils.error_handling import StarkErrorCode

from ape_starknet.config import DEFAULT_PORT, StarknetConfig
from ape_starknet.exceptions import StarknetProviderError
from ape_starknet.transactions import (
    AccountTransaction,
    DeclareTransaction,
    DeployAccountTransaction,
    InvokeFunctionTransaction,
    StarknetTransaction,
)
from ape_starknet.utils import (
    ALPHA_MAINNET_WL_DEPLOY_TOKEN_KEY,
    DEFAULT_ACCOUNT_SEED,
    DEVNET_ACCOUNT_START_BALANCE,
    EXECUTE_METHOD_NAME,
    EXECUTE_SELECTOR,
    PLUGIN_NAME,
    get_chain_id,
    get_class_hash,
    get_dict_from_tx_info,
    handle_client_errors,
    run_until_complete,
    to_checksum_address,
    to_int,
)
from ape_starknet.utils.basemodel import StarknetBase


class DevnetClient:
    def __init__(self, host_address: str):
        self.session = Session()
        self.host_address = host_address

    @cached_property
    def predeployed_accounts(self) -> List[Dict]:
        return self._get("predeployed_accounts")

    def increase_time(self, amount: int):
        return self._post("increase_time", json={"time": amount})

    def create_block(self):
        return self._post("create_block")

    def set_time(self, amount: int):
        return self._post("set_time", json={"time": amount})

    def mint(self, address: str, amount: int):
        return self._post("mint", json={"address": address, "amount": amount})

    def _get(self, uri: str, **kwargs):
        return self._request("get", uri, **kwargs)

    def _post(self, uri: str, **kwargs):
        return self._request("post", uri, **kwargs)

    def _request(self, method: str, uri: str, **kwargs):
        response = self.session.request(method.upper(), url=f"{self.host_address}/{uri}", **kwargs)
        response.raise_for_status()
        return response.json()


class StarknetProvider(ProviderAPI, StarknetBase):
    """
    A Starknet provider.
    """

    # Gets set when 'connect()' is called.
    client: Optional[GatewayClient] = None
    cached_code: Dict[int, ContractCode] = {}

    # Use int address to be free from duplicate keys.
    local_nonce_cache: Dict[int, int] = {}

    @property
    def connected_client(self) -> GatewayClient:
        if not self.client:
            raise ProviderNotConnectedError()

        return self.client

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
            self.client = self._create_client()

        return was_successful

    @property
    def starknet_client(self) -> GatewayClient:
        if not self.is_connected:
            raise StarknetProviderError("Provider is not connected to Starknet.")

        return self.client

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
        self.client = self._create_client()

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
        return self.tokens.get_balance(address)

    @handle_client_errors
    def get_code(self, address: str) -> bytes:
        # NOTE: Always return truthy value for code so that Ape core works properly
        code = self.get_code_and_abi(address).bytecode or [ord(c) for c in "PROXY"]
        return b"".join([HexBytes(x) for x in code])

    @handle_client_errors
    def get_abi(self, address: str) -> List[Dict]:
        return self.get_code_and_abi(address).abi

    @handle_client_errors
    def get_nonce(self, address: RawAddress) -> int:
        if self.network.name != LOCAL_NETWORK_NAME:
            return self.connected_client.get_contract_nonce_sync(address)

        address_int = int(address) if isinstance(address, int) else int(address, 16)
        if address_int not in self.local_nonce_cache:
            nonce = self.connected_client.get_contract_nonce_sync(address)
            self.local_nonce_cache[address_int] = nonce

        return self.local_nonce_cache[address_int]

    @handle_client_errors
    def estimate_gas_cost(self, txn: StarknetTransaction) -> int:
        if isinstance(txn, InvokeFunctionTransaction):
            if not txn.is_prepared:
                txn = cast(InvokeFunctionTransaction, self.prepare_transaction(txn))

            if txn.method_abi.name != EXECUTE_METHOD_NAME:
                txn = txn.as_execute()

        if not txn.signature:
            # Signature is required to estimate gas, unfortunately.
            # the transaction is typically signed by this point, but not always.
            signed_txn = self.account_manager[txn.receiver].sign_transaction(txn)
            if signed_txn is not None:
                txn = cast(StarknetTransaction, signed_txn)

        starknet_object = txn.as_starknet_object()
        estimated_fee = self.connected_client.estimate_fee_sync(starknet_object)
        return estimated_fee.overall_fee

    @property
    def gas_price(self) -> int:
        """
        **NOTE**: Currently, the gas price is fixed to always be 100 gwei.
        """

        return self.conversion_manager.convert("100 gwei", int)

    @handle_client_errors
    def get_block(self, block_id: BlockID) -> BlockAPI:
        block = self._get_block(block_id)
        return self.starknet.decode_block(block)

    def _get_block(self, block_id: BlockID) -> StarknetBlock:
        if isinstance(block_id, bytes):
            block_id = to_int(block_id)

        if isinstance(block_id, (int, str)) and len(str(block_id)) >= 72:
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

        return self.starknet_client.get_block_sync(**{kwarg: block_id})

    @handle_client_errors
    def send_call(self, txn: TransactionAPI) -> bytes:
        if not isinstance(txn, InvokeFunctionTransaction):
            type_str = f"{txn.type!r}" if isinstance(txn.type, bytes) else str(txn.type)
            raise StarknetProviderError(
                f"Transaction must be from an invocation. Received type {type_str}."
            )

        starknet_obj = txn._as_call()
        return self.connected_client.call_contract_sync(starknet_obj)

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
    def get_receipt(
        self, txn_hash: str, transaction: Optional[TransactionAPI] = None
    ) -> ReceiptAPI:
        self.starknet_client.wait_for_tx_sync(txn_hash)
        txn_info, receipt = run_until_complete(
            self.starknet_client.get_transaction(txn_hash),
            self.starknet_client.get_transaction_receipt(tx_hash=txn_hash),
        )

        data = {**asdict(receipt), **get_dict_from_tx_info(txn_info)}
        was_deploy = False
        # Handle __execute__ overhead. User only cares for target ABI.
        if data.get("entry_point_selector") == EXECUTE_SELECTOR:
            num_calls = data["calldata"][0]
            if num_calls != 1:
                logger.warning("Multi-call not yet supported. Only parsing first receipt.")

            data["sender"] = data["contract_address"]
            data["contract_address"] = self.starknet.decode_address(data["calldata"][1])
            data["entry_point_selector"] = data["calldata"][2]
            stop_index = data["calldata"][3] + 1
            data["calldata"] = data["calldata"][4:stop_index]

        if not transaction:
            transaction = self.starknet.create_transaction(**data)

        if isinstance(transaction, DeployAccountTransaction):
            # The DeployAccountReceipt expects first-hand access to the contract address.
            data["contract_address"] = transaction.contract_address
        elif isinstance(transaction, InvokeFunctionTransaction):
            # Manually remove `contract_address`, as it always confused Pydantic because
            # of TransactionAPI's `contract_address` attribute, which is required but a different
            # concept than this (for deploys, it is the new contract address but for invoke, it's
            # the receiver).
            data["receiver"] = data.pop("contract_address")
            original_tx = transaction.original_transaction
            was_deploy = (
                original_tx is not None
                and original_tx.method_abi.name == "deployContract"
                and int(original_tx.receiver, 16) == int(self.universal_deployer.address, 16)
            )

        receipt = self.starknet.decode_receipt(
            {"provider": self, "transaction": transaction, **data}
        )

        if was_deploy:
            event_abi = self.universal_deployer.contract_type.events["ContractDeployed"]
            logs = list(receipt.decode_logs(event_abi))
            if not logs:
                raise StarknetProviderError("Failed to create contract.")

            # Set the receipt `contract_address` to the newly deployed contract's address,
            # mimicing how it works in Ethereum.
            receipt.contract_address = self.starknet.decode_address(logs[-1]["address"])

        return receipt

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

        receipt = self.get_receipt(response.transaction_hash, transaction=txn)
        if not isinstance(txn, AccountTransaction):
            return receipt

        sender_address = None
        if isinstance(txn, InvokeFunctionTransaction):
            # The real sender is the account contract address.
            sender_address = txn.receiver
        elif isinstance(txn, DeclareTransaction):
            sender_address = txn.sender
        elif isinstance(txn, DeployAccountTransaction):
            sender_address = to_checksum_address(txn.contract_address)

        if sender_address:
            address_int = int(sender_address, 16)
            if address_int in self.local_nonce_cache:
                self.local_nonce_cache[address_int] += 1
            else:
                # Trigger setting nonce via call
                _ = self.provider.get_nonce(address_int)

            total_cost = receipt.total_fees_paid + receipt.value
            if total_cost:
                self.tokens.update_cache(address_int, -total_cost)

        return receipt

    def _send_transaction(
        self, txn: TransactionAPI, token: Optional[str] = None
    ) -> SentTransactionResponse:
        if not isinstance(txn, StarknetTransaction):
            raise StarknetProviderError(
                "Unable to send non-Starknet transaction using a Starknet provider "
                f"(received type '{type(txn)}')."
            )
        elif (
            isinstance(txn, InvokeFunctionTransaction)
            and txn.method_abi.name != EXECUTE_METHOD_NAME
        ):
            raise StarknetProviderError(
                f"Can only send invoke transaction to an account {EXECUTE_METHOD_NAME} method."
            )

        env_token = os.environ.get(ALPHA_MAINNET_WL_DEPLOY_TOKEN_KEY)
        token = token or getattr(txn, "token", env_token)
        starknet_txn = txn.as_starknet_object()
        result = self.starknet_client.send_transaction_sync(starknet_txn, token=token)
        return result

    @raises_not_implemented
    def get_contract_logs(  # type: ignore[empty-body]
        self, log_filter: LogFilter
    ) -> Iterator[ContractLog]:
        pass

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        txn.chain_id = self.provider.chain_id

        # All preparation happens on the account side.
        if isinstance(txn, AccountTransaction) and not txn.is_prepared and txn.sender:
            account = self.account_container[txn.sender]
            return account.prepare_transaction(txn)

        return txn

    def get_virtual_machine_error(self, exception: Exception, **kwargs: Any) -> VirtualMachineError:
        txn = kwargs.get("txn")
        return VirtualMachineError(base_err=exception, txn=txn)

    def get_code_and_abi(self, address: Union[str, AddressType, int]) -> ContractCode:
        address_int = parse_address(address)

        # Cache code for faster look-up
        if address_int not in self.cached_code:
            try:
                code_and_abi = self.starknet_client.get_code_sync(address_int)
            except ContractNotFoundError:
                # Nothing deployed to this address.
                code_and_abi = ContractCode(bytecode=[], abi=[])

            self.cached_code[address_int] = code_and_abi

        return self.cached_code[address_int]

    def get_class_hash(self, address: AddressType) -> int:
        code = self.get_code_and_abi(address)
        return get_class_hash(code)

    def _create_client(self) -> GatewayClient:
        network = self.uri if self.network.name == LOCAL_NETWORK_NAME else self.network.name
        return GatewayClient(network)


class StarknetDevnetProvider(SubprocessProvider, StarknetProvider):
    """
    A subprocess provider for the starknet-devnet process.
    """

    @property
    def process_name(self) -> str:
        return "starknet-devnet"

    @cached_property
    def devnet_client(self) -> DevnetClient:
        return DevnetClient(self.uri)

    def connect(self):
        if self.network.name == LOCAL_NETWORK_NAME:
            # Behave like a 'SubprocessProvider'
            if not self.is_connected:
                super().connect()

            self.start()

            # Ensure test accounts get cached so they remain when switching providers.
            _ = self.account_container.test_accounts

        self.client = self._create_client()

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
            "--initial-balance",
            str(DEVNET_ACCOUNT_START_BALANCE),
        ]

    def set_timestamp(self, new_timestamp: int):
        if self.devnet_client is None:
            raise StarknetProviderError("Must be connected to starknet-devnet to use this feature.")

        result = self.devnet_client.set_time(new_timestamp)
        if "next_block_timestamp" not in result:
            raise StarknetProviderError(result)

    def mine(self, num_blocks: int = 1):
        for index in range(num_blocks):
            self.devnet_client.create_block()

    def set_balance(self, account: AddressType, amount: Union[int, float, str, bytes]):
        """
        Mint the difference between the account's current balance and the desired balance
        and give it to the account.
        """

        # Convert account
        if not isinstance(account, str):
            account = self.conversion_manager.convert(account, AddressType)

        # Convert amount
        if isinstance(amount, str) and " " in amount:
            # Convert values like "10 ETH"
            amount = self.conversion_manager.convert(amount, int)
        elif not isinstance(amount, int):
            amount = to_int(amount)

        amount = int(amount)  # for mypy
        current_balance = self.get_balance(account)
        difference = amount - current_balance
        if difference < 0:
            raise StarknetProviderError(
                f"Unable to set balance to {amount}, "
                f"as it is less than the current balance of {current_balance}."
            )

        self.devnet_client.mint(account, difference)
        self.tokens.update_cache(account, difference)


__all__ = ["StarknetProvider", "StarknetDevnetProvider"]
