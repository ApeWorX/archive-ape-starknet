import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import click
from ape.api import AccountAPI, AccountContainerAPI, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import AccountsError
from ape.logging import logger
from ape.types import AddressType, MessageSignature, SignableMessage, TransactionSignature
from ape.utils import cached_property
from eth_keyfile import create_keyfile_json, decode_keyfile_json  # type: ignore
from eth_utils import text_if_str, to_bytes
from ethpm_types.abi import ConstructorABI
from hexbytes import HexBytes
from starknet_py.net import KeyPair  # type: ignore
from starknet_py.net.account.compiled_account_contract import (  # type: ignore
    COMPILED_ACCOUNT_CONTRACT,
)
from starkware.crypto.signature.signature import get_random_private_key  # type: ignore
from starkware.starknet.services.api.contract_definition import ContractDefinition  # type: ignore


class StarknetAccountContracts(AccountContainerAPI):

    ephemeral_accounts: Dict[str, Dict] = {}
    """Local-network accounts that do not persist."""

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
    def accounts(self) -> Iterator[AccountAPI]:
        for alias, account_data in self.ephemeral_accounts.items():
            yield StarknetEphemeralAccount(raw_account_data=account_data, account_key=alias)

        for key_file_path in self._key_file_paths:
            yield StarknetKeyfileAccount(key_file_path=key_file_path)

    def __len__(self) -> int:
        return len([*self._key_file_paths])

    def __setitem__(self, address: AddressType, account: AccountAPI):
        pass

    def __delitem__(self, address: AddressType):
        pass

    def load(self, alias: str) -> "BaseStarknetAccount":
        if alias in self.ephemeral_accounts:
            return StarknetEphemeralAccount(
                raw_account_data=self.ephemeral_accounts[alias], account_key=alias
            )

        return self.load_key_file_account(alias)

    def load_key_file_account(self, alias: str) -> "StarknetKeyfileAccount":
        for key_file_path in self._key_file_paths:
            if key_file_path.stem == alias:
                return StarknetKeyfileAccount(key_file_path=key_file_path)

        raise AccountsError(f"Starknet account '{alias}' not found.")

    def deploy_account(self, alias: str, private_key: Optional[int] = None) -> str:
        """
        Deploys an account contract for the given alias.

        Args:
            alias (str): The alias to use to reference the account in ``ape``.
            private_key (Optional[int]): Optionally provide your own private key.`

        Returns:
            str: The contract address of the account.
        """

        if alias in self.aliases:
            raise AccountsError(f"Account with alias '{alias}' already exists.")

        network_name = self.provider.network.name
        logger.info(f"Deploying an account to '{network_name}' network ...")

        private_key = private_key or get_random_private_key()
        key_pair = KeyPair.from_private_key(private_key)

        account_contract = ContractDefinition.loads(COMPILED_ACCOUNT_CONTRACT)
        constructor_abi_data: Dict = next(
            (member for member in account_contract.abi if member["type"] == "constructor"),
            {},
        )

        constructor_abi = ConstructorABI(**constructor_abi_data)
        transaction = self.provider.network.ecosystem.encode_deployment(
            HexBytes(account_contract.serialize()), constructor_abi, key_pair.public_key
        )
        receipt = self.provider.send_transaction(transaction)

        if not receipt.contract_address:
            raise AccountsError("Failed to deploy account contract.")

        deployment_data = {
            "deployments": [
                {"network_name": network_name, "contract_address": receipt.contract_address},
            ],
        }

        if self.provider.network.name == LOCAL_NETWORK_NAME:
            account_data = {
                "public_key": key_pair.public_key,
                "private_key": key_pair.private_key,
                **deployment_data,
            }
            self.ephemeral_accounts[alias] = account_data
        else:
            # Only write keyfile if not in a local network
            path = self.data_folder.joinpath(f"{alias}.json")
            StarknetKeyfileAccount.write(path, key_pair, **deployment_data)

        return receipt.contract_address

    def delete_account(self, alias: str):
        if alias in self.ephemeral_accounts:
            del self.ephemeral_accounts[alias]
        else:
            account = self.load_key_file_account(alias)
            account.delete()


@dataclass
class StarknetAccountDeployment:
    network_name: str
    contract_address: AddressType


class BaseStarknetAccount(AccountAPI):
    @property
    def contract_address(self) -> AddressType:
        return self.network_manager.starknet.decode_address(self.account_data["contract_address"])

    @property
    def address(self) -> AddressType:
        return self.network_manager.starknet.decode_address(self.account_data["public_key"])

    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        return None  # TODO

    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionSignature]:
        return None  # TODO

    def deploy(self, contract: ContractContainer, *args, **kwargs) -> ContractInstance:
        return contract.deploy(sender=self)

    @property
    def deployments(self) -> List[StarknetAccountDeployment]:
        return [StarknetAccountDeployment(**d) for d in self.account_data["deployments"]]


class StarknetEphemeralAccount(BaseStarknetAccount):
    raw_account_data: Dict
    account_key: str

    @property
    def account_data(self) -> Dict:
        return self.raw_account_data

    @property
    def alias(self) -> Optional[str]:
        return self.account_key

    @property
    def __key(self) -> HexBytes:
        return self.raw_account_data["private_key"]


class StarknetKeyfileAccount(BaseStarknetAccount):
    key_file_path: Path
    locked: bool = True
    __cached_key: Optional[HexBytes] = None

    @classmethod
    def write(cls, path: Path, key_pair: KeyPair, **kwargs):
        passphrase = click.prompt("Enter a passphrase", hide_input=True, confirmation_prompt=True)
        key_file_data = cls.__encrypt_key_file(passphrase, key_pair.private_key)
        key_file_data["public_key"] = key_file_data["address"]
        del key_file_data["address"]
        account_data = {**key_file_data, **kwargs}
        path.write_text(json.dumps(account_data))

    @property
    def alias(self) -> Optional[str]:
        return self.key_file_path.stem

    @cached_property
    def account_data(self) -> Dict:
        return json.loads(self.key_file_path.read_text())

    def delete(self):
        passphrase = click.prompt(
            f"Enter Passphrase to delete '{self.alias}'",
            hide_input=True,
        )
        self.__decrypt_key_file(passphrase)
        self.key_file_path.unlink()

    @property
    def __key(self) -> HexBytes:
        if self.__cached_key is not None:
            if not self.locked:
                click.echo(f"Using cached key for '{self.alias}'")
                return self.__cached_key
            else:
                self.__cached_key = None

        passphrase = click.prompt(
            f"Enter Passphrase to unlock '{self.alias}'",
            hide_input=True,
            default="",  # Just in case there's no passphrase
        )

        key = self.__decrypt_key_file(passphrase)

        if click.confirm(f"Leave '{self.alias}' unlocked?"):
            self.locked = False
            self.__cached_key = key

        return key

    @classmethod
    def __encrypt_key_file(cls, passphrase: str, private_key: int) -> Dict:
        key_bytes = HexBytes(private_key)
        passphrase_bytes = text_if_str(to_bytes, passphrase)
        return create_keyfile_json(key_bytes, passphrase_bytes, kdf="scrypt")

    def __decrypt_key_file(self, passphrase: str) -> HexBytes:
        key_file_dict = json.loads(self.key_file_path.read_text())
        key_file_dict["address"] = key_file_dict["public_key"]
        del key_file_dict["public_key"]
        password_bytes = text_if_str(to_bytes, passphrase)
        return HexBytes(decode_keyfile_json(key_file_dict, password_bytes))
