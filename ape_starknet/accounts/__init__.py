import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Union

import click
from ape.api import AccountAPI, AccountContainerAPI, ReceiptAPI, TransactionAPI
from ape.api.address import BaseAddress
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import AccountsError
from ape.logging import logger
from ape.types import AddressType, SignableMessage
from ape.utils import abstractmethod
from eth_keyfile import create_keyfile_json, decode_keyfile_json  # type: ignore
from eth_utils import text_if_str, to_bytes
from hexbytes import HexBytes
from starknet_py.net import KeyPair  # type: ignore
from starknet_py.net.account.account_client import AccountClient  # type: ignore
from starknet_py.net.account.compiled_account_contract import (  # type: ignore
    COMPILED_ACCOUNT_CONTRACT,
)
from starknet_py.utils.crypto.cpp_bindings import ECSignature  # type: ignore
from starknet_py.utils.crypto.facade import sign_calldata  # type: ignore
from starkware.cairo.lang.vm.cairo_runner import verify_ecdsa_sig  # type: ignore
from starkware.crypto.signature.signature import get_random_private_key  # type: ignore

from ape_starknet._utils import (
    ALPHA_MAINNET_WL_DEPLOY_TOKEN_KEY,
    PLUGIN_NAME,
    get_chain_id,
    handle_client_errors,
)
from ape_starknet.provider import StarknetProvider
from ape_starknet.tokens import TokenManager
from ape_starknet.transactions import InvokeFunctionTransaction, StarknetTransaction

APP_KEY_FILE_KEY = "ape-starknet"
"""
The key-file stanza containing custom properties
specific to the ape-starknet plugin.
"""
APP_KEY_FILE_VERSION = "0.1.0"


class StarknetAccountContracts(AccountContainerAPI):

    ephemeral_accounts: Dict[str, Dict] = {}
    """Local-network accounts that do not persist."""

    cached_accounts: Dict[str, "StarknetKeyfileAccount"] = {}

    @property
    def _key_file_paths(self) -> Iterator[Path]:
        return self.data_folder.glob("*.json")

    @property
    def aliases(self) -> Iterator[str]:
        for key in self.ephemeral_accounts.keys():
            yield key

        for key_file in self._key_file_paths:
            yield key_file.stem

    @property
    def public_key_addresses(self) -> Iterator[AddressType]:
        for account in self.accounts:
            yield account.address

    @property
    def accounts(self) -> Iterator[AccountAPI]:
        for alias, account_data in self.ephemeral_accounts.items():
            yield StarknetEphemeralAccount(raw_account_data=account_data, account_key=alias)

        for key_file_path in self._key_file_paths:
            if key_file_path.stem in self.cached_accounts:
                yield self.cached_accounts[key_file_path.stem]
            else:
                account = StarknetKeyfileAccount(key_file_path=key_file_path)
                self.cached_accounts[key_file_path.stem] = account
                yield account

    def __len__(self) -> int:
        return len([*self._key_file_paths])

    def __setitem__(self, address: AddressType, account: AccountAPI):
        pass

    def __delitem__(self, address: AddressType):
        pass

    def __getitem__(self, item: Union[AddressType, int]) -> AccountAPI:
        address: AddressType = (
            self.network_manager.starknet.decode_address(item) if isinstance(item, int) else item
        )

        # First, assume it is the contract address
        for account in self.accounts:
            if not isinstance(account, BaseStarknetAccount):
                continue

            contract_address = account.contract_address
            if contract_address and contract_address == address:
                return super().__getitem__(account.address)

        # First, use the account's public key (what Ape is used to).
        return super().__getitem__(address)

    def load(self, alias: str) -> "BaseStarknetAccount":
        if alias in self.ephemeral_accounts:
            account = StarknetEphemeralAccount(
                raw_account_data=self.ephemeral_accounts[alias], account_key=alias
            )
            return account

        return self.load_key_file_account(alias)

    def load_key_file_account(self, alias: str) -> "StarknetKeyfileAccount":
        if alias in self.cached_accounts:
            return self.cached_accounts[alias]

        for key_file_path in self._key_file_paths:
            if key_file_path.stem == alias:
                account = StarknetKeyfileAccount(key_file_path=key_file_path)
                self.cached_accounts[alias] = account
                return account

        raise AccountsError(f"Starknet account '{alias}' not found.")

    def import_account_from_key_file(self, alias: str, key_file: Path):
        if not key_file.is_file():
            raise AccountsError(f"Unknown keyfile '{key_file}'.")

        destination = self.data_folder.joinpath(f"{alias}.json")
        if destination.exists():
            raise AccountsError(f"Account already saved with alias '{alias}'.")

        key_file_data = json.loads(key_file.read_text())
        if "argent" in key_file_data and APP_KEY_FILE_KEY not in key_file_data:
            # Migrate Argent-X keyfile

            deployments = []
            for account in key_file_data["argent"]["accounts"]:
                network = _clean_network_name(account["network"])
                deployment = StarknetAccountDeployment(
                    network_name=network, contract_address=account["address"]
                )
                deployments.append(vars(deployment))

            key_file_data = {**key_file_data, **_create_key_file_app_data(deployments)}

        destination.write_text(json.dumps(key_file_data))

    def import_account(
        self,
        alias: str,
        network_name: str,
        contract_address: str,
        private_key: Union[int, str],
    ):
        if isinstance(private_key, str):
            private_key = private_key.strip("'\"")
            private_key = int(private_key, 16)

        network_name = _clean_network_name(network_name)
        key_pair = KeyPair.from_private_key(private_key)
        deployments = [{"network_name": network_name, "contract_address": contract_address}]

        if network_name == LOCAL_NETWORK_NAME:
            account_data = {
                "address": key_pair.public_key,
                "private_key": key_pair.private_key,
                **_create_key_file_app_data(deployments),
            }
            self.ephemeral_accounts[alias] = account_data
        else:
            # Only write keyfile if not in a local network
            path = self.data_folder.joinpath(f"{alias}.json")
            new_account = StarknetKeyfileAccount(key_file_path=path)
            new_account.write(passphrase=None, private_key=private_key, deployments=deployments)

    def deploy_account(
        self, alias: str, private_key: Optional[int] = None, token: Optional[str] = None
    ) -> str:
        """
        Deploys an account contract for the given alias.

        Args:
            alias (str): The alias to use to reference the account in ``ape``.
            private_key (Optional[int]): Optionally provide your own private key.`
            token (Optional[str]): Used for deploying contracts in Alpha MainNet.

        Returns:
            str: The contract address of the account.
        """

        if alias in self.aliases:
            raise AccountsError(f"Account with alias '{alias}' already exists.")

        network_name = self.provider.network.name
        logger.info(f"Deploying an account to '{network_name}' network ...")

        private_key = private_key or get_random_private_key()
        key_pair = KeyPair.from_private_key(private_key)

        contract_address = self.provider._deploy(  # type: ignore
            COMPILED_ACCOUNT_CONTRACT, key_pair.public_key, token=token
        )
        self.import_account(alias, network_name, contract_address, key_pair.private_key)
        return contract_address

    def delete_account(
        self, alias: str, network: Optional[str] = None, passphrase: Optional[str] = None
    ):
        network = _clean_network_name(network) if network else self.provider.network.name
        if alias in self.ephemeral_accounts:
            del self.ephemeral_accounts[alias]
        else:
            account = self.load_key_file_account(alias)
            account.delete(network, passphrase=passphrase)


@dataclass
class StarknetAccountDeployment:
    network_name: str
    contract_address: AddressType


class BaseStarknetAccount(AccountAPI):
    token_manager: TokenManager = TokenManager()

    @abstractmethod
    def _get_key(self) -> int:
        ...

    @abstractmethod
    def get_account_data(self) -> Dict:
        ...

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.contract_address}>"

    @property
    def contract_address(self) -> Optional[AddressType]:
        ecosystem = self.network_manager.ecosystems[PLUGIN_NAME]
        for deployment in self.get_deployments():
            network_name = deployment.network_name
            network = ecosystem.networks[network_name]
            if network_name == network.name:
                address = deployment.contract_address
                return ecosystem.decode_address(address)

        return None

    @property
    def address(self) -> AddressType:
        public_key = self.get_account_data()["address"]
        return self.network_manager.starknet.decode_address(public_key)

    @property
    def provider(self) -> StarknetProvider:
        provider = super().provider
        if not isinstance(provider, StarknetProvider):
            # Mostly for mypy
            raise AccountsError("Must use a Starknet provider.")

        return provider

    def sign_transaction(self, txn: TransactionAPI) -> Optional[ECSignature]:
        if not isinstance(txn, InvokeFunctionTransaction):
            raise AccountsError("This account can only sign Starknet transactions.")

        starknet_object = txn.as_starknet_object()
        return self.sign_message(starknet_object.calldata)

    def transfer(
        self,
        account: Union[str, AddressType, BaseAddress],
        value: Union[str, int, None] = None,
        data: Union[bytes, str, None] = None,
        **kwargs,
    ) -> ReceiptAPI:
        value = value or 0
        value = self.conversion_manager.convert(value, int) or 0
        if not isinstance(value, int):
            if value.isnumeric():
                value = str(value)
            else:
                raise ValueError("value is not an integer.")

        if not isinstance(account, str) and hasattr(account, "contract_address"):
            account = account.contract_address  # type: ignore

        if not isinstance(account, int):
            account = self.provider.network.ecosystem.encode_address(account)  # type: ignore

        if self.contract_address is None:
            raise ValueError("Contract address cannot be None")

        sender = self.provider.network.ecosystem.encode_address(self.contract_address)
        return self.token_manager.transfer(sender, account, value, **kwargs)  # type: ignore

    def deploy(self, contract: ContractContainer, *args, **kwargs) -> ContractInstance:
        return contract.deploy(sender=self)

    @handle_client_errors
    def send_transaction(self, txn: TransactionAPI, token: Optional[str] = None) -> ReceiptAPI:
        if not token and hasattr(txn, "token") and txn.token:  # type: ignore
            token = txn.token  # type: ignore
        else:
            token = os.environ.get(ALPHA_MAINNET_WL_DEPLOY_TOKEN_KEY)

        if not isinstance(txn, StarknetTransaction):
            # Mostly for mypy
            raise AccountsError("Can only send Starknet transactions.")

        account_client = self.create_account_client()
        starknet_txn = txn.as_starknet_object()
        txn_info = account_client.add_transaction_sync(starknet_txn, token=token)
        txn_hash = txn_info["transaction_hash"]
        return self.provider.get_transaction(txn_hash)

    def create_account_client(self) -> AccountClient:
        network = self.provider.network
        key_pair = KeyPair(
            public_key=network.ecosystem.encode_address(self.address),
            private_key=self._get_key(),
        )
        chain_id = get_chain_id(network.name)
        return AccountClient(
            self.contract_address,
            key_pair,
            self.provider.uri,
            chain=chain_id,
        )

    def get_deployment(self, network_name: str) -> Optional[StarknetAccountDeployment]:
        for deployment in self.get_deployments():
            if deployment.network_name in network_name:
                return deployment

        return None

    def check_signature(  # type: ignore
        self,
        data: int,
        signature: Optional[ECSignature] = None,  # TransactionAPI doesn't need it
    ) -> bool:
        int_address = self.network_manager.get_ecosystem(PLUGIN_NAME).encode_address(self.address)
        return verify_ecdsa_sig(int_address, data, signature)

    def get_deployments(self) -> List[StarknetAccountDeployment]:
        plugin_key_file_data = self.get_account_data()[APP_KEY_FILE_KEY]
        return [StarknetAccountDeployment(**d) for d in plugin_key_file_data["deployments"]]


class StarknetEphemeralAccount(BaseStarknetAccount):
    raw_account_data: Dict
    account_key: str

    def get_account_data(self) -> Dict:
        return self.raw_account_data

    @property
    def alias(self) -> Optional[str]:
        return self.account_key

    def _get_key(self) -> int:
        if "private_key" not in self.raw_account_data:
            raise AccountsError("This account cannot sign.")

        return self.raw_account_data["private_key"]

    def sign_message(self, msg: SignableMessage) -> Optional[ECSignature]:
        if not isinstance(msg, (list, tuple)):
            msg = [msg]

        return sign_calldata(msg, self._get_key())


class StarknetKeyfileAccount(BaseStarknetAccount):
    key_file_path: Path
    locked: bool = True
    __cached_key: Optional[int] = None

    def write(
        self,
        passphrase: Optional[str] = None,
        private_key: Optional[int] = None,
        deployments: Optional[List[Dict]] = None,
    ):
        passphrase = (
            click.prompt("Enter a new passphrase", hide_input=True, confirmation_prompt=True)
            if passphrase is None
            else passphrase
        )
        key_file_data = self.__encrypt_key_file(passphrase, private_key=private_key)
        account_data = self.get_account_data()
        if deployments:
            if APP_KEY_FILE_KEY not in account_data:
                account_data[APP_KEY_FILE_KEY] = {}

            account_data[APP_KEY_FILE_KEY]["deployments"] = deployments

        account_data = {**account_data, **key_file_data}
        self.key_file_path.write_text(json.dumps(account_data))

    @property
    def alias(self) -> Optional[str]:
        return self.key_file_path.stem

    def get_account_data(self) -> Dict:
        if self.key_file_path.is_file():
            return json.loads(self.key_file_path.read_text())

        return {}

    def delete(self, network: str, passphrase: Optional[str] = None):
        passphrase = (
            click.prompt(
                f"Enter passphrase to delete '{self.alias}'",
                hide_input=True,
            )
            if passphrase is None
            else passphrase
        )

        try:
            self.__decrypt_key_file(passphrase)
        except FileNotFoundError:
            return

        network = _clean_network_name(network)
        deployments = self.get_deployments()
        if network not in [d.network_name for d in deployments]:
            raise AccountsError(f"Account '{self.alias}' not deployed to network '{network}'.")

        remaining_deployments = [
            vars(d) for d in self.get_deployments() if d.network_name != network
        ]
        if not remaining_deployments:
            # Delete entire account JSON if no more deployments.
            # The user has to agree to an additional prompt since this may be very destructive.

            if click.confirm(f"Completely delete local key for account '{self.address}'?"):
                self.key_file_path.unlink()
        else:
            self.write(passphrase=passphrase, deployments=remaining_deployments)

    def sign_message(
        self, msg: SignableMessage, passphrase: Optional[str] = None
    ) -> Optional[ECSignature]:
        if not isinstance(msg, (list, tuple)):
            msg = [msg]

        private_key = self._get_key(passphrase=passphrase)
        return sign_calldata(msg, private_key)

    def change_password(self):
        self.locked = True  # force entering passphrase to get key
        original_passphrase = self._get_passphrase_from_prompt()
        private_key = self._get_key(passphrase=original_passphrase)
        self.write(passphrase=None, private_key=private_key)

    def add_deployment(self, network_name: str, contract_address: AddressType):
        passphrase = self._get_passphrase_from_prompt()
        network_name = _clean_network_name(network_name)
        deployments = [
            vars(d) for d in self.get_deployments() if d.network_name not in network_name
        ]
        new_deployment = StarknetAccountDeployment(
            network_name=network_name, contract_address=contract_address
        )
        deployments.append(vars(new_deployment))

        self.write(
            passphrase=passphrase,
            private_key=self._get_key(passphrase=passphrase),
            deployments=deployments,
        )

    def _get_key(self, passphrase: Optional[str] = None) -> int:
        if self.__cached_key is not None:
            if not self.locked:
                click.echo(f"Using cached key for '{self.alias}'")
                return self.__cached_key
            else:
                self.__cached_key = None

        if passphrase is None:
            passphrase = self._get_passphrase_from_prompt()

        key_hex_str = self.__decrypt_key_file(passphrase).hex()
        key = int(key_hex_str, 16)
        if self.locked and (
            passphrase is not None or click.confirm(f"Leave '{self.alias}' unlocked?")
        ):
            self.locked = False
            self.__cached_key = key

        return key

    def _get_passphrase_from_prompt(self) -> str:
        return click.prompt(
            f"Enter passphrase to unlock '{self.alias}'",
            hide_input=True,
            default="",  # Just in case there's no passphrase
        )

    def __encrypt_key_file(self, passphrase: str, private_key: Optional[int] = None) -> Dict:
        private_key = self._get_key(passphrase=passphrase) if private_key is None else private_key
        key_bytes = HexBytes(private_key)
        passphrase_bytes = text_if_str(to_bytes, passphrase)
        return create_keyfile_json(key_bytes, passphrase_bytes, kdf="scrypt")

    def __decrypt_key_file(self, passphrase: str) -> HexBytes:
        key_file_dict = json.loads(self.key_file_path.read_text())
        password_bytes = text_if_str(to_bytes, passphrase)
        decoded_json = decode_keyfile_json(key_file_dict, password_bytes)
        return HexBytes(decoded_json)


def _clean_network_name(network: str) -> str:
    for net in ("local", "mainnet", "testnet"):
        if net in network:
            return net

    if "goerli" in network:
        return "testnet"

    return network


def _create_key_file_app_data(deployments: List[Dict[str, str]]) -> Dict:
    return {APP_KEY_FILE_KEY: {"version": APP_KEY_FILE_VERSION, "deployments": deployments}}


__all__ = [
    "StarknetAccountContracts",
    "StarknetEphemeralAccount",
    "StarknetKeyfileAccount",
]
