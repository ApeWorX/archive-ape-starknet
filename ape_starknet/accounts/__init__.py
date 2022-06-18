import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Union

import click
from ape.api import AccountAPI, AccountContainerAPI, ReceiptAPI, TransactionAPI
from ape.api.address import BaseAddress
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import AccountsError, ProviderError, SignatureError
from ape.logging import logger
from ape.types import AddressType, SignableMessage, TransactionSignature
from ape.utils import abstractmethod, cached_property
from eth_keyfile import create_keyfile_json, decode_keyfile_json  # type: ignore
from eth_utils import text_if_str, to_bytes
from ethpm_types import ContractType
from ethpm_types.abi import MethodABI
from hexbytes import HexBytes
from services.external_api.client import BadRequest  # type: ignore
from starknet_py.net import KeyPair  # type: ignore
from starknet_py.net.account.compiled_account_contract import (  # type: ignore
    COMPILED_ACCOUNT_CONTRACT,
)
from starknet_py.net.signer.stark_curve_signer import StarkCurveSigner  # type: ignore
from starknet_py.utils.crypto.facade import ECSignature, sign_calldata  # type: ignore
from starkware.cairo.lang.vm.cairo_runner import verify_ecdsa_sig  # type: ignore
from starkware.crypto.signature.signature import get_random_private_key  # type: ignore

from ape_starknet.tokens import TokenManager
from ape_starknet.transactions import InvokeFunctionTransaction
from ape_starknet.utils import PLUGIN_NAME, get_chain_id
from ape_starknet.utils.basemodel import StarknetMixin

APP_KEY_FILE_KEY = "ape-starknet"
"""
The key-file stanza containing custom properties
specific to the ape-starknet plugin.
"""
APP_KEY_FILE_VERSION = "0.1.0"


class StarknetAccountContracts(AccountContainerAPI, StarknetMixin):

    ephemeral_accounts: Dict[str, Dict] = {}
    """Local-network accounts that do not persist."""

    cached_accounts: Dict[str, "StarknetKeyfileAccount"] = {}

    @property
    def _key_file_paths(self) -> Iterator[Path]:
        return self.data_folder.glob("*.json")

    @property
    def aliases(self) -> Iterator[str]:
        yield from self.ephemeral_accounts.keys()
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

    def get_account(self, address: Union[AddressType, int]) -> "BaseStarknetAccount":
        return self[address]  # type: ignore

    def load(self, alias: str) -> "BaseStarknetAccount":
        if alias in self.ephemeral_accounts:
            return StarknetEphemeralAccount(
                raw_account_data=self.ephemeral_accounts[alias], account_key=alias
            )

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

        # Add account contract to cache
        address = self.starknet.decode_address(contract_address)
        if self.network_manager.active_provider and self.provider.network.explorer:
            # Skip errors when unable to store contract type.
            with contextlib.suppress(ProviderError, BadRequest):
                contract_type = self.provider.network.explorer.get_contract_type(address)
                if contract_type:
                    self.chain_manager.contracts[address] = contract_type

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


class BaseStarknetAccount(AccountAPI, StarknetMixin):
    token_manager: TokenManager = TokenManager()

    @abstractmethod
    def _get_key(self) -> int:
        ...

    @abstractmethod
    def get_account_data(self) -> Dict:
        ...

    @property
    def contract_address(self) -> Optional[AddressType]:
        for deployment in self.get_deployments():
            network_name = deployment.network_name
            network = self.starknet.networks[network_name]
            if network_name == network.name:
                address = deployment.contract_address
                return self.starknet.decode_address(address)

        return None

    @property
    def address(self) -> AddressType:
        public_key = self.get_account_data()["address"]
        return self.starknet.decode_address(public_key)

    @cached_property
    def signer(self) -> StarkCurveSigner:
        key_pair = KeyPair.from_private_key(self._get_key())
        network = self.provider.network
        chain_id = get_chain_id(network.name)
        return StarkCurveSigner(
            account_address=self.contract_address, key_pair=key_pair, chain_id=chain_id
        )

    @cached_property
    def contract_type(self) -> Optional[ContractType]:
        if not self.contract_address:
            # Contract not deployed to this network yet
            return None

        contract_type = self.chain_manager.contracts.get(self.contract_address)
        if not contract_type:
            raise AccountsError(f"Account '{self.contract_address}' was expected but not found.")

        return contract_type

    @cached_property
    def execute_abi(self) -> Optional[MethodABI]:
        contract_address = self.contract_address
        contract_type = self.contract_type
        if not contract_address or not contract_type:
            return None

        execute_abi_ls = [
            abi for abi in contract_type.abi if getattr(abi, "name", "") == "__execute__"
        ]
        if not execute_abi_ls:
            raise AccountsError(f"Account '{contract_address}' does not have __execute__ method.")

        abi = execute_abi_ls[0]
        if not isinstance(abi, MethodABI):
            raise AccountsError("ABI for '__execute__' is not a method.")

        return abi

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.contract_address}>"

    def call(self, txn: TransactionAPI, send_everything: bool = False) -> ReceiptAPI:
        if send_everything:
            raise NotImplementedError("send_everything currently isn't implemented in Starknet.")

        if not isinstance(txn, InvokeFunctionTransaction):
            raise AccountsError("Can only call Starknet transactions.")

        txn = self.prepare_transaction(txn)
        if not txn.signature:
            raise SignatureError("The transaction was not signed.")

        return self.provider.send_transaction(txn)

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        contract_address = self.contract_address
        execute_abi = self.execute_abi
        if not contract_address or not execute_abi:
            raise AccountsError(
                f"Account is not deployed to network '{self.provider.network.name}'."
            )

        if not isinstance(txn, InvokeFunctionTransaction):
            raise AccountsError("Can only prepare invoke transactions.")

        txn: InvokeFunctionTransaction = super().prepare_transaction(txn)  # type: ignore
        stark_tx = txn.as_starknet_object()
        account_call = {
            "to": stark_tx.contract_address,
            "selector": stark_tx.entry_point_selector,
            "data_offset": 0,
            "data_len": len(stark_tx.calldata),
        }
        txn.data = [[account_call], stark_tx.calldata, self.nonce]
        txn.receiver = contract_address
        txn.sender = None
        txn.method_abi = execute_abi
        txn.signature = self.sign_transaction(txn)
        return txn

    def sign_transaction(self, txn: TransactionAPI) -> TransactionSignature:
        if not isinstance(txn, InvokeFunctionTransaction):
            raise AccountsError("This account can only sign Starknet transactions.")

        # NOTE: 'v' is not used
        sign_result = self.signer.sign_transaction(txn.as_starknet_object())
        if not sign_result:
            raise SignatureError("Failed to sign transaction.")

        r = to_bytes(sign_result[0])
        s = to_bytes(sign_result[1])
        return TransactionSignature(v=0, r=r, s=s)  # type: ignore

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
            account = self.starknet.encode_address(account)  # type: ignore

        if self.contract_address is None:
            raise ValueError("Contract address cannot be None")

        sender = self.starknet.encode_address(self.contract_address)
        return self.token_manager.transfer(sender, account, value, **kwargs)  # type: ignore

    def deploy(self, contract: ContractContainer, *args, **kwargs) -> ContractInstance:
        return contract.deploy(sender=self)

    def get_deployment(self, network_name: str) -> Optional[StarknetAccountDeployment]:
        return next(
            (
                deployment
                for deployment in self.get_deployments()
                if deployment.network_name in network_name
            ),
            None,
        )

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
        if remaining_deployments:
            self.write(passphrase=passphrase, deployments=remaining_deployments)
        elif click.confirm(f"Completely delete local key for account '{self.address}'?"):
            # Delete entire account JSON if no more deployments.
            # The user has to agree to an additional prompt since this may be very destructive.
            self.key_file_path.unlink()

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
