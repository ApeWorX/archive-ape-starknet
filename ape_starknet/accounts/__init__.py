import functools
import json
import random
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Union

import click
from ape.api import AccountAPI, AccountContainerAPI, ReceiptAPI, TransactionAPI
from ape.api.address import BaseAddress
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractContainer
from ape.exceptions import AccountsError, SignatureError
from ape.logging import LogLevel, logger
from ape.types import AddressType, SignableMessage, TransactionSignature
from ape.utils import abstractmethod, cached_property
from eth_keyfile import create_keyfile_json, decode_keyfile_json
from eth_typing import HexAddress, HexStr
from eth_utils import add_0x_prefix, text_if_str, to_bytes
from ethpm_types import ContractType
from ethpm_types.abi import MethodABI
from hexbytes import HexBytes
from starknet_py.net import KeyPair
from starknet_py.net.account.compiled_account_contract import COMPILED_ACCOUNT_CONTRACT
from starknet_py.net.signer.stark_curve_signer import StarkCurveSigner
from starknet_py.utils.crypto.facade import ECSignature, message_signature, pedersen_hash
from starkware.cairo.lang.vm.cairo_runner import verify_ecdsa_sig
from starkware.crypto.signature.signature import private_to_stark_key
from starkware.starknet.core.os.contract_address.contract_address import (
    calculate_contract_address_from_hash,
)
from starkware.starknet.services.api.contract_class import ContractClass

from ape_starknet.exceptions import StarknetProviderError
from ape_starknet.tokens import TokenManager
from ape_starknet.transactions import InvokeFunctionTransaction
from ape_starknet.utils import (
    convert_contract_class_to_contract_type,
    get_chain_id,
    get_random_private_key,
    pad_hex_str,
)
from ape_starknet.utils.basemodel import StarknetBase

APP_KEY_FILE_KEY = "ape-starknet"
"""
The key-file stanza containing custom properties
specific to the ape-starknet plugin.
"""
APP_KEY_FILE_VERSION = "0.1.0"
OZ_CONTRACT_CLASS = ContractClass.loads(COMPILED_ACCOUNT_CONTRACT)
OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE = convert_contract_class_to_contract_type(OZ_CONTRACT_CLASS)

# https://github.com/starkware-libs/cairo-lang/blob/v0.9.1/src/starkware/starknet/cli/starknet_cli.py#L66
FEE_MARGIN_OF_ESTIMATION = 1.1


def sign_calldata(calldata: Iterable[int], priv_key: int):
    """
    Helper function that signs hash:

        hash = pedersen_hash(calldata[0], 0)
        hash = pedersen_hash(calldata[1], hash)
        hash = pedersen_hash(calldata[2], hash)
        ...

    :param calldata: iterable of ints
    :param priv_key: private key
    :return: signed calldata's hash
    """
    hashed_calldata = functools.reduce(lambda x, y: pedersen_hash(y, x), calldata, 0)
    return message_signature(hashed_calldata, priv_key)


class StarknetAccountContracts(AccountContainerAPI, StarknetBase):

    ephemeral_accounts: Dict[str, Dict] = {}
    """Local-network accounts that do not persist."""

    cached_accounts: Dict[str, "StarknetKeyfileAccount"] = {}
    """Accounts created in a live network that persist in key-files."""

    @property
    def provider_config(self) -> Dict:
        return self.starknet_config["provider"]

    @property
    def number_of_devnet_accounts(self) -> int:
        if not self.network_manager.active_provider:
            return 0

        if self.provider.network.name != LOCAL_NETWORK_NAME:
            return 0

        return self.provider_config.local["number_of_accounts"]  # type: ignore

    @property
    def devnet_account_seed(self) -> int:
        return self.provider_config.local["seed"]  # type: ignore

    @property
    def _key_file_paths(self) -> Iterator[Path]:
        for path in self.data_folder.glob("*.json"):
            if path.stem not in ("deployments_map",):
                yield path

    @property
    def aliases(self) -> Iterator[str]:
        yield from self.ephemeral_accounts.keys()
        for key_file in self._key_file_paths:
            yield key_file.stem

    @property
    def public_key_addresses(self) -> Iterator[AddressType]:
        for account in self.accounts:
            yield account.address

    @cached_property
    def test_accounts(self) -> List["StarknetDevnetAccount"]:
        random_generator = random.Random()
        random_generator.seed(self.devnet_account_seed)
        devnet_accounts = [
            StarknetDevnetAccount(private_key=random_generator.getrandbits(128))
            for _ in range(self.number_of_devnet_accounts)
        ]

        # Track all devnet account contracts in chain manager for look-up purposes
        for account in devnet_accounts:
            self.chain_manager.contracts[account.address] = account.get_contract_type()

        return devnet_accounts

    @property
    def accounts(self) -> Iterator[AccountAPI]:
        for test_account in self.test_accounts:
            yield test_account

        for alias, account_data in self.ephemeral_accounts.items():
            yield StarknetEphemeralAccount(raw_account_data=account_data, account_key=alias)

        for key_file_path in self._key_file_paths:
            if key_file_path.stem == "deployments_map":
                continue

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
        address = HexAddress(HexStr(HexBytes(item).hex())) if isinstance(item, int) else item

        # First, check if user accessing via public key
        for account in self.accounts:
            if not isinstance(account, BaseStarknetAccount):
                continue

            if account.public_key == address:
                return super().__getitem__(account.address)

        # Else, use the contract address (more expected)
        checksum_address = self.starknet.decode_address(address)
        return super().__getitem__(checksum_address)

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
        passphrase: Optional[str] = None,
    ):
        address = self.starknet.decode_address(contract_address)
        if isinstance(private_key, str) and private_key.startswith("0x"):
            private_key = pad_hex_str(private_key.strip("'\""))
            private_key = int(private_key, 16)
        elif isinstance(private_key, str):
            private_key = int(private_key)

        network_name = _clean_network_name(network_name)
        key_pair = KeyPair.from_private_key(private_key)
        deployments = [{"network_name": network_name, "contract_address": address}]

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
            new_account.write(
                passphrase=passphrase, private_key=private_key, deployments=deployments
            )

        # Ensure contract gets cached
        network = self.starknet.get_network(network_name)
        with network.use_provider(network.default_provider or "starknet"):
            contract_type = self.starknet_explorer.get_contract_type(address)
            if not contract_type:
                raise StarknetProviderError(f"Failed to get contract type for account '{address}'.")

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

        private_key = private_key or int(get_random_private_key(), 16)
        key_pair = KeyPair.from_private_key(private_key)

        account_container = ContractContainer(contract_type=OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE)
        instance = account_container.deploy(key_pair.public_key, token=token)
        self.import_account(alias, network_name, instance.address, key_pair.private_key)
        return instance.address

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


class BaseStarknetAccount(AccountAPI, StarknetBase):
    token_manager: TokenManager = TokenManager()

    @abstractmethod
    def _get_key(self) -> int:
        ...

    @abstractmethod
    def get_account_data(self) -> Dict:
        ...

    @abstractmethod
    def get_contract_type(self) -> ContractType:
        ...

    @property
    def address(self) -> AddressType:
        for deployment in self.get_deployments():
            network_name = deployment.network_name
            network = self.starknet.networks[network_name]
            if network_name == network.name:
                contract_address = deployment.contract_address
                return self.starknet.decode_address(contract_address)

        raise AccountsError("Account not deployed.")

    @property
    def address_int(self) -> int:
        return self.starknet.encode_address(self.address)

    @property
    def public_key(self) -> str:
        account_data = self.get_account_data()
        if "address" not in account_data:
            raise StarknetProviderError(
                f"Account data corrupted, missing 'address' key: {account_data}."
            )

        address = account_data["address"]
        if isinstance(address, int):
            address = HexBytes(address).hex()

        return add_0x_prefix(address)

    @cached_property
    def signer(self) -> StarkCurveSigner:
        key_pair = KeyPair.from_private_key(self._get_key())
        return StarkCurveSigner(
            account_address=self.address,
            key_pair=key_pair,
            chain_id=get_chain_id(self.provider.chain_id),
        )

    @cached_property
    def execute_abi(self) -> Optional[MethodABI]:
        contract_type = self.get_contract_type()
        if not contract_type:
            return None

        execute_abi_ls = [
            abi for abi in contract_type.abi if getattr(abi, "name", "") == "__execute__"
        ]
        if not execute_abi_ls:
            raise AccountsError(f"Account '{self.address}' does not have __execute__ method.")

        abi = execute_abi_ls[0]
        if not isinstance(abi, MethodABI):
            raise AccountsError("ABI for '__execute__' is not a method.")

        return abi

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.address}>"

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
        self._prepare_transaction(txn)
        if txn.max_fee is None:
            # NOTE: Signature cannot be None when estimating fees.
            txn.signature = self.sign_transaction(txn)
            txn.max_fee = ceil(self.get_fee_estimate(txn) * FEE_MARGIN_OF_ESTIMATION)

        txn.signature = self.sign_transaction(txn)
        return txn

    def get_fee_estimate(self, txn: TransactionAPI) -> int:
        return self.provider.estimate_gas_cost(txn)

    def _prepare_transaction(self, txn: TransactionAPI):
        execute_abi = self.execute_abi
        if not execute_abi:
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
        contract_type = self.chain_manager.contracts[self.address]
        txn.data = self.starknet.encode_calldata(
            contract_type.abi, execute_abi, [[account_call], stark_tx.calldata, self.nonce]
        )
        txn.receiver = self.address
        txn.sender = None
        txn.original_method_abi = txn.method_abi
        txn.method_abi = execute_abi

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
                raise StarknetProviderError("value is not an integer.")

        if not isinstance(account, str) and hasattr(account, "address"):
            receiver = getattr(account, "address")

        elif isinstance(account, str):
            checksummed_address = self.starknet.decode_address(account)
            receiver = self.starknet.encode_address(checksummed_address)

        elif isinstance(account, int):
            receiver = account

        else:
            raise TypeError(f"Unable to handle account type '{type(account)}'.")

        return self.token_manager.transfer(self.address, receiver, value, **kwargs)

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
        public_key_int = self.starknet.encode_address(self.public_key)
        return verify_ecdsa_sig(public_key_int, data, signature)

    def get_deployments(self) -> List[StarknetAccountDeployment]:
        plugin_key_file_data = self.get_account_data().get(APP_KEY_FILE_KEY, {})
        return [StarknetAccountDeployment(**d) for d in plugin_key_file_data.get("deployments", [])]


class StarknetDevelopmentAccount(BaseStarknetAccount):
    def get_contract_type(self) -> ContractType:
        return OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE

    def sign_message(self, msg: SignableMessage) -> Optional[ECSignature]:
        if not isinstance(msg, (list, tuple)):
            msg = [msg]

        return sign_calldata(msg, self._get_key())  # type: ignore


class StarknetDevnetAccount(StarknetDevelopmentAccount):
    """
    Accounts generated in the starknet-devnet process.
    """

    private_key: int

    @cached_property
    def public_key_int(self) -> int:
        return private_to_stark_key(self.private_key)

    @cached_property
    def public_key(self) -> str:
        return add_0x_prefix(HexStr(HexBytes(self.public_key_int).hex()))

    @cached_property
    def address(self) -> AddressType:
        address_int = calculate_contract_address_from_hash(
            # Hardcoded values since devnet 0.2.6:
            # https://github.com/Shard-Labs/starknet-devnet/blob/v0.2.6/starknet_devnet/account.py#L36
            salt=20,
            class_hash=1803505466663265559571280894381905521939782500874858933595227108099796801620,
            constructor_calldata=[self.public_key_int],
            deployer_address=0,
        )
        return self.starknet.decode_address(address_int)

    def _get_key(self) -> int:
        return self.private_key

    def get_account_data(self) -> Dict:
        deployments = [
            {
                "contract_address": self.address,
                "network_name": LOCAL_NETWORK_NAME,
            }
        ]
        return {
            "private_key": self.private_key,
            "public_key": self.public_key,
            APP_KEY_FILE_KEY: {"deployments": deployments},
        }


class StarknetEphemeralAccount(StarknetDevelopmentAccount):
    """
    Accounts deployed on a local Starknet chain.
    """

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


class StarknetKeyfileAccount(BaseStarknetAccount):
    key_file_path: Path
    locked: bool = True
    __autosign: bool = False
    __cached_key: Optional[int] = None

    @property
    def alias(self) -> Optional[str]:
        return self.key_file_path.stem

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        self._prepare_transaction(txn)
        do_relock = False
        if not txn.max_fee:
            if self.locked:
                # Unlock to prevent multiple prompts for signing transaction.
                original_level = logger.level
                logger.set_level(LogLevel.ERROR)
                self.set_autosign(True)
                logger.set_level(original_level)

            txn.signature = self.sign_transaction(txn)
            txn.max_fee = ceil(self.get_fee_estimate(txn) * FEE_MARGIN_OF_ESTIMATION)

        txn.signature = self.sign_transaction(txn)

        if do_relock:
            self.locked = True
            self.set_autosign(False)

        return txn

    def get_contract_type(self) -> ContractType:
        return OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE

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
        return sign_calldata(msg, private_key)  # type: ignore

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

    def unlock(self, passphrase: Optional[str] = None):
        passphrase = passphrase or self._get_passphrase_from_prompt(
            f"Enter passphrase to unlock '{self.alias}'"
        )
        self._get_key(passphrase=passphrase)
        self.locked = False

    def set_autosign(self, enabled: bool, passphrase: Optional[str] = None):
        if enabled:
            self.unlock(passphrase=passphrase)
            logger.warning("Danger! This account will now sign any transaction its given.")

        self.__autosign = enabled
        if not enabled:
            # Re-lock if was turning off
            self.locked = True
            self.__cached_key = None

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

    def _get_passphrase_from_prompt(self, message: Optional[str] = None) -> str:
        message = message or f"Enter passphrase to unlock '{self.alias}'"
        return click.prompt(
            message,
            hide_input=True,
            default="",  # Just in case there's no passphrase
        )

    def __encrypt_key_file(self, passphrase: str, private_key: Optional[int] = None) -> Dict:
        private_key = self._get_key(passphrase=passphrase) if private_key is None else private_key
        key_str = pad_hex_str(HexBytes(private_key).hex())
        passphrase_bytes = text_if_str(to_bytes, passphrase)
        return create_keyfile_json(HexBytes(key_str), passphrase_bytes, kdf="scrypt")

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
