import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from ape.api import AccountAPI, AccountContainerAPI, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import AccountsError
from ape.logging import logger
from ape.types import AddressType, MessageSignature, SignableMessage, TransactionSignature
from ape.utils import abstractmethod, cached_property
from ethpm_types.abi import ConstructorABI
from hexbytes import HexBytes
from starknet_py.net import KeyPair  # type: ignore
from starknet_py.net.account.compiled_account_contract import (
    COMPILED_ACCOUNT_CONTRACT,  # type: ignore
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
        return len([*self._key_files])

    def __setitem__(self, address: AddressType, account: AccountAPI):
        pass

    def __delitem__(self, address: AddressType):
        pass

    def load(self, alias: str) -> "BaseStarknetAccount":
        if alias in self.ephemeral_accounts:
            return StarknetEphemeralAccount(self.ephemeral_accounts[alias])

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

        account_data = {
            "deployments": [
                {"network_name": network_name, "contract_address": receipt.contract_address},
            ],
            "private_key": key_pair.private_key,
            "public_key": key_pair.public_key,
        }

        if self.provider.network.name == LOCAL_NETWORK_NAME:
            self.ephemeral_accounts[alias] = account_data
        else:
            # Only write keyfile if not in a local network
            path = self.data_folder.joinpath(f"{alias}.json")
            path.write_text(json.dumps(account_data))

        return receipt.contract_address

    def delete_account(self, alias: str):
        if alias in self.ephemeral_accounts:
            del self.ephemeral_accounts[alias]

        else:
            account = self.load_key_file_account(alias)
            account.key_file_path.unlink(missing_ok=True)


@dataclass
class StarknetAccountDeployment:
    network_name: str
    contract_address: AddressType


class BaseStarknetAccount(AccountAPI):
    @abstractmethod
    def account_data(self) -> Dict:
        ...

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


class StarknetKeyfileAccount(BaseStarknetAccount):
    key_file_path: Path

    @property
    def alias(self) -> Optional[str]:
        return self.key_file_path.stem

    @cached_property
    def account_data(self) -> Dict:
        return json.loads(self.key_file_path.read_text())
