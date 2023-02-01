import json
from abc import abstractmethod
from math import ceil
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union, cast

import click
from ape.api import AccountAPI, AccountContainerAPI, ReceiptAPI, TransactionAPI
from ape.api.address import BaseAddress
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import APINotImplementedError, ProviderNotConnectedError, SignatureError
from ape.logging import logger
from ape.types import AddressType, TransactionSignature
from ape.utils import ZERO_ADDRESS, cached_property
from ape.utils.basemodel import BaseModel
from eth_keyfile import create_keyfile_json, decode_keyfile_json
from eth_utils import text_if_str, to_bytes, to_hex
from ethpm_types import ContractType
from hexbytes import HexBytes
from pydantic import Field, validator
from starknet_py.net.signer.stark_curve_signer import StarkCurveSigner
from starknet_py.utils.crypto.facade import ECSignature, message_signature
from starkware.cairo.lang.vm.cairo_runner import verify_ecdsa_sig
from starkware.starknet.core.os.contract_address.contract_address import (
    calculate_contract_address_from_hash,
)
from starkware.starknet.definitions.fields import ContractAddressSalt

from ape_starknet.config import NetworkConfig
from ape_starknet.exceptions import ContractTypeNotFoundError, StarknetAccountsError
from ape_starknet.provider import StarknetDevnetProvider, StarknetProvider
from ape_starknet.transactions import (
    AccountTransaction,
    DeployAccountTransaction,
    InvokeFunctionTransaction,
    StarknetTransaction,
)
from ape_starknet.types import StarknetSignableMessage
from ape_starknet.utils import (
    ARGENTX_ACCOUNT_CLASS_HASH,
    ARGENTX_ACCOUNT_SOURCE_ID,
    DEVNET_ACCOUNT_START_BALANCE,
    MAX_FEE,
    OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH,
    OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE,
    OPEN_ZEPPELIN_ACCOUNT_SOURCE_ID,
    create_keypair,
    get_account_constructor_calldata,
    get_chain_id,
    get_random_private_key,
    pad_hex_str,
    to_checksum_address,
    to_int,
)
from ape_starknet.utils.basemodel import StarknetBase

APP_KEY_FILE_KEY = "ape-starknet"
"""
The key-file stanza containing custom properties
specific to the ape-starknet plugin.
"""
APP_KEY_FILE_VERSION = "0.1.0"

# https://github.com/starkware-libs/cairo-lang/blob/v0.9.1/src/starkware/starknet/cli/starknet_cli.py#L66
FEE_MARGIN_OF_ESTIMATION = 1.1

DEVNET_CONTRACT_SALT = 20


class StarknetAccountContainer(AccountContainerAPI, StarknetBase):

    ephemeral_accounts: Dict[str, Dict] = {}
    """Local-network accounts that do not persist."""

    cached_accounts: Dict[str, "StarknetKeyfileAccount"] = {}
    """Accounts created in a live network that persist in key-files."""

    @property
    def provider_config(self) -> NetworkConfig:
        return self.starknet_config["provider"]

    @property
    def number_of_devnet_accounts(self) -> int:
        if not self.network_manager.active_provider:
            return 0

        if self.provider.network.name != LOCAL_NETWORK_NAME:
            return 0

        return int(self.provider_config.local["number_of_accounts"])

    @property
    def devnet_account_seed(self) -> int:
        return self.provider_config.local["seed"]

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

    @property
    def test_accounts(self) -> List["StarknetDevelopmentAccount"]:
        if "genesis_test_accounts" in self.__dict__:
            return self.genesis_test_accounts

        if (
            self.network_manager.active_provider is None
            or self.provider.network.name != LOCAL_NETWORK_NAME
            or not isinstance(self.provider, StarknetProvider)
        ):
            return []

        return self.genesis_test_accounts

    @cached_property
    def genesis_test_accounts(self) -> List:
        provider = self.provider
        if not isinstance(provider, StarknetDevnetProvider):
            return []

        try:
            predeployed_accounts = provider.devnet_client.predeployed_accounts
        except ProviderNotConnectedError:
            logger.warning("Devnet not running")
            return []

        devnet_accounts = [StarknetDevelopmentAccount(**acc) for acc in predeployed_accounts]

        # Caching.
        for account in devnet_accounts:
            self.chain_manager.contracts[account.address] = account.contract_type
            self.tokens.balance_cache[account.address_int] = {
                self.starknet.fee_token_symbol.lower(): DEVNET_ACCOUNT_START_BALANCE
            }

        return devnet_accounts

    @property
    def accounts(self) -> Iterator[AccountAPI]:
        for test_account in self.test_accounts:
            yield test_account

        for alias, account_data in self.ephemeral_accounts.items():
            yield StarknetDevelopmentAccount(**account_data)

        for key_file_path in self._key_file_paths:
            if key_file_path.stem == "deployments_map":
                continue

            if key_file_path.stem in self.cached_accounts:
                yield self.cached_accounts[key_file_path.stem]
            else:
                account = StarknetKeyfileAccount.from_file(key_file_path)
                self.cached_accounts[key_file_path.stem] = account
                yield account

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"

    def __len__(self) -> int:
        return len([*self._key_file_paths])

    def __setitem__(self, address: AddressType, account: AccountAPI):
        pass

    def __delitem__(self, address: AddressType):
        pass

    def __getitem__(self, item: Union[AddressType, int]) -> AccountAPI:
        address_int = item if isinstance(item, int) else to_int(item)

        for account in [a for a in self.accounts if isinstance(a, BaseStarknetAccount)]:
            if to_int(account.public_key) == address_int:
                # Matched by public key.
                return account

            elif to_int(account.address) == address_int:
                # Matched by contract address.
                return account

        raise IndexError(f"No local account {item}.")

    def __contains__(self, address: Union[AddressType, int]) -> bool:
        try:
            self.__getitem__(address)
            return True

        except IndexError:
            return False

    def get_account(self, address: Union[AddressType, int]) -> "BaseStarknetAccount":
        return self[address]  # type: ignore

    def load(self, alias: str) -> "BaseStarknetAccount":
        if alias in self.ephemeral_accounts:
            return StarknetDevelopmentAccount(**self.ephemeral_accounts[alias])

        return self.load_key_file_account(alias)

    def load_key_file_account(self, alias: str) -> "StarknetKeyfileAccount":
        if alias in self.cached_accounts:
            return self.cached_accounts[alias]

        for key_file_path in self._key_file_paths:
            if key_file_path.stem == alias:
                account = StarknetKeyfileAccount.from_file(key_file_path)
                self.cached_accounts[alias] = account
                return account

        raise StarknetAccountsError(f"Starknet account '{alias}' not found.")

    def create_account(
        self,
        alias: str,
        class_hash: int = OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH,
        salt: Optional[int] = None,
        private_key: Optional[str] = None,
        constructor_calldata: Optional[List[int]] = None,
        allow_local_file_store: bool = False,
    ) -> "BaseStarknetAccount":
        if alias in self.aliases:
            raise StarknetAccountsError(f"Account with alias '{alias}' already exists.")

        private_key = private_key or get_random_private_key()
        salt = salt or ContractAddressSalt.get_random_value()

        if class_hash == OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH:
            class_hash_msg = OPEN_ZEPPELIN_ACCOUNT_SOURCE_ID
        elif class_hash == ARGENTX_ACCOUNT_CLASS_HASH:
            class_hash_msg = ARGENTX_ACCOUNT_SOURCE_ID
        else:
            class_hash_msg = str(class_hash)

        logger.info(f"Creating account using class hash '{class_hash_msg}' ...")
        account = self.import_account(
            alias,
            class_hash,
            private_key,
            salt=salt,
            constructor_calldata=constructor_calldata,
            allow_local_file_store=allow_local_file_store,
        )

        if (
            self.network_manager.active_provider
            and self.provider.network.name == LOCAL_NETWORK_NAME
            and not allow_local_file_store
        ):
            # Auto-matically deploy local accounts (unless triggered by the CLI).
            self.provider.set_balance(account.address, DEVNET_ACCOUNT_START_BALANCE)
            account.deploy_account()

        return account

    def import_account(
        self,
        alias: str,
        class_hash: int,
        private_key: Union[int, str],
        deployments: Optional[List["StarknetAccountDeployment"]] = None,
        constructor_calldata: Optional[List] = None,
        salt: Optional[int] = None,
        allow_local_file_store: bool = False,
    ) -> "BaseStarknetAccount":
        deployments = deployments or []
        key_pair = create_keypair(private_key)
        self._cache_deployments(class_hash, deployments)

        account_data: Dict[str, Any] = {
            "public_key": key_pair.public_key,
            "private_key": key_pair.private_key,
            "class_hash": class_hash,
        }
        account_data[
            "constructor_calldata"
        ] = constructor_calldata or get_account_constructor_calldata(key_pair, class_hash)

        if (
            not allow_local_file_store
            and not deployments
            and self.network_manager.active_provider is not None
            and self.provider.network.name == LOCAL_NETWORK_NAME
        ):
            # Locally simulating keypair creation without any deployments.
            self.ephemeral_accounts[alias] = account_data
            return StarknetDevelopmentAccount(**account_data)

        new_account: Optional["BaseStarknetAccount"] = None
        local_deployments = [x for x in deployments if x.network_name == LOCAL_NETWORK_NAME]
        local_salt = salt or DEVNET_CONTRACT_SALT
        for local_deployment in local_deployments:
            account_data["salt"] = local_salt
            account_data["address"] = local_deployment.contract_address
            self.ephemeral_accounts[alias] = account_data
            new_account = StarknetDevelopmentAccount(**account_data)

        live_deployments = [x for x in deployments if x not in local_deployments]
        if not allow_local_file_store and not live_deployments and new_account:
            # Using a local network and ephemeral accounts in development mode.
            return new_account

        # The deployments contained an actual live network. Use that as the return account.
        salt = salt or ContractAddressSalt.get_random_value()
        path = self.data_folder.joinpath(f"{alias}.json")
        is_local = (
            self.network_manager.active_provider
            and self.provider.network.name == LOCAL_NETWORK_NAME
        )
        new_account = StarknetKeyfileAccount._from_import(
            path,
            is_local=is_local,
            get_pass=lambda: self._prompt_for_new_passphrase(alias),
            allow_local_file_store=allow_local_file_store,
            class_hash=class_hash,
            constructor_calldata=constructor_calldata,
            deployments=live_deployments,
            private_key=key_pair.private_key,
            salt=salt,
        )
        self.cached_accounts[alias] = new_account
        return new_account

    def _prompt_for_new_passphrase(self, alias: str):
        return click.prompt(
            f"Create passphrase to encrypt account '{alias}'",
            hide_input=True,
            default="",  # Just in case there's no passphrase
            show_choices=False,
            confirmation_prompt=True,
        )

    def delete_account(
        self,
        alias: str,
        address: Optional[Union[AddressType, int]] = None,
        networks: Optional[Union[str, List[str]]] = None,
        leave_unlocked: Optional[bool] = None,
    ):
        if alias in self.ephemeral_accounts:
            # Only 1 local deployment for ephemeral accounts.
            del self.ephemeral_accounts[alias]

        else:
            # Live network - delegate to account.
            account = self.load_key_file_account(alias)
            account.delete(
                networks=networks,
                address=address,
                leave_unlocked=leave_unlocked,
            )

    def _cache_deployments(self, class_hash: int, deployments: List["StarknetAccountDeployment"]):
        for deployment in deployments:
            contract_type = None
            address = deployment.contract_address
            # Cache contract type for the account.
            network_obj = self.starknet.get_network(deployment.network_name)
            if class_hash == OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH:
                contract_type = OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE

            else:
                with network_obj.use_provider(network_obj.default_provider or "starknet"):
                    contract_type = self.starknet_explorer.get_contract_type_from_provider(address)

            # Only cache of contract type has a name or else caching gets messsed up.
            if contract_type and contract_type.name:
                self.chain_manager.contracts[address] = contract_type


class StarknetAccountDeployment(BaseModel):
    network_name: str
    contract_address: AddressType
    salt: Optional[int] = None  # Only should be None when unknown.

    def __eq__(self, other):
        other_id = None
        if hasattr(other, "path_id"):
            other_id = other.path_id
        elif isinstance(other, dict):
            other_id = self.make_path_id(other["network_name"], other["contract_address"])
        elif isinstance(other, str):
            parts = other.split(":")
            other_id = self.make_path_id(parts[0], parts[1])

        return self.path_id == other_id

    @validator("contract_address", pre=True)
    def validate_contract_address(cls, value):
        return to_checksum_address(value)

    @validator("network_name", pre=True)
    def validate_network_name(cls, value):
        return _clean_network_name(value)

    @property
    def path_id(self) -> str:
        return self.make_path_id(self.network_name, self.contract_address)

    @classmethod
    def make_path_id(cls, network: str, address: Union[str, int]) -> str:
        return f"{network}:{to_int(address)}"


class BaseStarknetAccount(AccountAPI, StarknetBase):
    @property
    def salt(self) -> int:
        """
        The salt is used to determine the contract address. If you change the salt
        but keep the class hash and calldata the same, you will get a new address.
        To keep addresses consistent across networks, a single salt value exists
        at the root of an account. However, when deploying an account on live
        networks, you will have the option to change the salt for each deployment.
        """

        raise NotImplementedError("Salt must be implemented by base class.")

    @property
    def class_hash(self) -> int:
        # Overriden in subclasses.
        return OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH

    @property
    def deployed(self, network_name: Optional[str] = None) -> bool:
        return True

    @property
    def public_key(self) -> str:
        raise APINotImplementedError("Implement `public_key` in a base class.")

    @cached_property
    def public_key_int(self) -> int:
        return to_int(self.public_key)

    @property
    def address_int(self) -> int:
        return self.starknet.encode_address(self.address)

    @property
    def deployments(self) -> List[StarknetAccountDeployment]:
        return []  # Overriden

    @cached_property
    def default_address(self) -> AddressType:
        return to_checksum_address(self.default_address_int)

    @cached_property
    def default_address_int(self) -> int:
        """
        The contract address (int) calculated from the class hash, root contract
        address salt, and constructor calldata.
        """

        return self.get_contract_address()

    @property
    def constructor_calldata(self) -> List[Any]:
        return [] if self.class_hash == ARGENTX_ACCOUNT_CLASS_HASH else [self.public_key_int]

    @cached_property
    def contract_type(self) -> ContractType:
        if self.class_hash == OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH:
            return OPEN_ZEPPELIN_ACCOUNT_CONTRACT_TYPE

        contract_type = self.starknet_explorer.get_contract_type_from_provider(self.address)
        if not contract_type:
            raise ContractTypeNotFoundError(self.address)

        if self.class_hash == ARGENTX_ACCOUNT_CLASS_HASH:
            contract_type.name = "ArgentAccount"
            contract_type.source_id = ARGENTX_ACCOUNT_SOURCE_ID

        else:
            contract_type.name = f"Account_{self.class_hash}"
            contract_type.source_id = ARGENTX_ACCOUNT_SOURCE_ID

        return contract_type

    def get_contract_address(self, salt: Optional[int] = None) -> int:
        """
        Calculate a contract address for the given account's salt, class hash,
        and constructor data.

        Args:
            salt(Optional[salt]): Salt to use. Defaults to the root account salt.
              Note: accounts use a root default salt to have consistent addresses
              accross different networks.

        Returns:
            int: The contract address.
        """

        return calculate_contract_address_from_hash(
            class_hash=self.class_hash,
            constructor_calldata=self.constructor_calldata,
            deployer_address=0,
            salt=salt or self.salt,
        )

    def get_deploy_account_txn(self, salt: Optional[int] = None) -> DeployAccountTransaction:
        txn = DeployAccountTransaction(
            salt=salt or self.salt,
            class_hash=self.class_hash,
            constructor_calldata=self.constructor_calldata,
            signature=None,
        )

        # Set the receiver to the transaction can be prepared properly.
        txn.receiver = (
            self.starknet.decode_address(txn.contract_address)
            if txn.contract_address is not None
            else txn.receiver
        )

        return txn

    def __repr__(self):
        try:
            suffix = str(self.address)
        except StarknetAccountsError as err:
            suffix = str(err)

        return f"<{self.__class__.__name__} {suffix}>"

    @abstractmethod
    def add_deployment(self, network_name: str, contract_address: int, salt: int):
        pass

    def call(
        self, txn: TransactionAPI, send_everything: bool = False, **signer_options
    ) -> ReceiptAPI:
        if send_everything:
            raise NotImplementedError("send_everything currently isn't implemented in Starknet.")

        elif not isinstance(txn, AccountTransaction):
            raise StarknetAccountsError("Can only call Starknet account transactions.")

        # Ensure account is deployed first. Else, try to do that first.
        if not self.deployed:
            logger.warning("Account not yet deployed! Attempting to deploy now.")
            self.deploy_account()

        txn = self.prepare_transaction(txn)
        if not txn.signature:
            raise SignatureError("The transaction was not signed.")

        return self.provider.send_transaction(txn)

    def deploy(  # type: ignore[override]
        self,
        contract: Union[ContractContainer, "BaseStarknetAccount"],
        *args,
        publish: bool = False,
        **kwargs,
    ) -> Union[ContractInstance, ReceiptAPI]:
        if isinstance(contract, ContractContainer):
            return super().deploy(contract, *args, publish=publish, **kwargs)

        if contract.alias == self.alias:
            return self.deploy_account(**kwargs)

        raise ValueError(f"Unable to deploy '{contract}'.")

    def deploy_account(
        self, funder: Optional["BaseStarknetAccount"] = None, salt: Optional[int] = None
    ) -> ReceiptAPI:
        """
        Deploys this account.

        Args:
            funder (Optional[:class:`~ape_starknet.accounts.BaseStarknetAccount`]):
              An account to use to assist in funding the deployment. Only requests
              transfer if needed.
            salt (Optional[int]): Contract address salt. Needed if wanting to deploy
              to a different address.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`: The receipt from the
            :class:`~ape_starknet.transactions.DeployAccountTransaction`.
        """
        txn = self.get_deploy_account_txn(salt)

        # NOTE: Because of error handling Ape core, need to trick Ape into thinking
        # the account balance is actually the funder's.
        original_enabled_value = self.tokens.cache_enabled.get(self.provider.network.name, False)
        self.tokens.cache_enabled[self.provider.network.name] = True
        balance = self.balance
        fee_token = self.starknet.fee_token_symbol.lower()
        address = self.address_int
        if funder:
            if address not in self.tokens.balance_cache:
                self.tokens.balance_cache[address] = {}

            self.tokens.balance_cache[address][fee_token] = funder.balance

        # The fee estimation and signing happen here.
        txn = cast(DeployAccountTransaction, self.prepare_transaction(txn))

        if funder:
            # Reset new account balance in cache to its correct amount.
            self.tokens.balance_cache[address][fee_token] = balance

            if balance < txn.max_fee:
                # Use funder to provide the rest.
                amount = ceil((txn.max_fee - balance) * FEE_MARGIN_OF_ESTIMATION)
                self.tokens.transfer(funder, txn.contract_address, amount)
                logger.success("Account has been funded.")

        elif balance < txn.max_fee:
            raise StarknetAccountsError("Unable to afford transaction.")

        self.tokens.cache_enabled[self.provider.network.name] = original_enabled_value
        receipt = self.provider.send_transaction(txn)
        self.add_deployment(self.provider.network.name, txn.contract_address, txn.salt)
        return receipt

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        if not isinstance(txn, AccountTransaction):
            return txn

        txn.max_fee = txn.max_fee or MAX_FEE
        txn = self._prepare_transaction(txn)
        signed_txn = self.sign_transaction(txn)
        if signed_txn is not None:
            return cast(TransactionAPI, signed_txn)
        return txn

    def _prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        if isinstance(txn, AccountTransaction):
            # Set now to prevent infinite loop
            txn.is_prepared = True

        txn.nonce = self.nonce
        txn = super().prepare_transaction(txn)
        if isinstance(txn, InvokeFunctionTransaction):
            return txn.as_execute()

        return txn

    def get_fee_estimate(self, txn: TransactionAPI) -> int:
        return self.provider.estimate_gas_cost(txn)

    def handle_signature(self, sign_result, txn: TransactionAPI) -> TransactionAPI:
        if not sign_result:
            raise SignatureError("Failed to sign transaction.")

        r = to_bytes(sign_result[0])
        s = to_bytes(sign_result[1])
        txn.signature = TransactionSignature(v=0, r=r, s=s)
        self.check_signature(txn)
        return txn

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
                raise StarknetAccountsError("Transfer value is not an integer.")

        if not isinstance(account, str) and hasattr(account, "address"):
            receiver = getattr(account, "address")

        elif isinstance(account, str):
            checksummed_address = self.starknet.decode_address(account)
            receiver = self.starknet.encode_address(checksummed_address)

        elif isinstance(account, int):
            receiver = account

        else:
            raise TypeError(f"Unable to handle account type '{type(account)}'.")

        if receiver == ZERO_ADDRESS:
            raise StarknetAccountsError("Cannot transfer to ZERO_ADDRESS.")

        return self.tokens.transfer(self.address, receiver, value, **kwargs)

    def check_signature(  # type: ignore
        self,
        data: Union[int, List[int], TransactionAPI, StarknetSignableMessage],
        signature: Optional[ECSignature] = None,
    ) -> bool:
        if isinstance(data, TransactionAPI):
            if not signature and data.signature:
                signature = data.signature

            data = to_int(data.txn_hash)

        elif isinstance(data, StarknetSignableMessage):
            data = data.hash

        else:
            data = StarknetSignableMessage(message=data).hash

        signature = [*signature] if signature else []
        if len(signature) == 3:
            # Trim unused version
            signature = signature[1:]

        signature = [to_int(x) for x in signature]
        return verify_ecdsa_sig(self.public_key_int, data, signature)

    def declare(self, contract_type: ContractType):
        txn = self.starknet.encode_contract_blueprint(contract_type, sender=self.address)
        return self.call(txn)

    def _create_signer(self, private_key: int) -> StarkCurveSigner:
        key_pair = create_keypair(private_key)
        return StarkCurveSigner(
            account_address=self.address,
            key_pair=key_pair,
            chain_id=get_chain_id(self.provider.chain_id),
        )


class StarknetDevelopmentAccount(BaseStarknetAccount):
    contract_address: Optional[AddressType] = Field(None, alias="address")
    """
    The contract address of the account.
    If not set, calculates it based on other properties.
    """

    private_key: str
    """The account's private key."""

    # Alias because base-class needs `public_key` as a @property
    pub_key: str = Field(alias="public_key")
    """
    The public key of the account. Aliased from ``public_key`` because that is
    a ``@property`` in the base class.
    """

    cls_hash: int = Field(OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH, alias="class_hash")

    custom_constructor_calldata: Optional[List[Any]] = Field(None, alias="constructor_calldata")
    custom_salt: Optional[int] = None
    is_deployed: bool = False

    @validator("contract_address", "pub_key", "private_key", pre=True, allow_reuse=True)
    def validate_int_to_hex(cls, value):
        return to_checksum_address(value)

    @property
    def salt(self) -> int:
        return self.custom_salt if self.custom_salt is not None else DEVNET_CONTRACT_SALT

    @property
    def public_key(self) -> str:
        return self.pub_key

    @property
    def address(self) -> AddressType:
        if not self.contract_address:
            self.contract_address = self.default_address

        return self.contract_address

    @property
    def class_hash(self) -> int:
        return self.cls_hash

    @property
    def deployments(self) -> List[StarknetAccountDeployment]:
        return (
            [
                StarknetAccountDeployment(
                    network_name=LOCAL_NETWORK_NAME, contract_address=self.address, salt=self.salt
                )
            ]
            if self.is_deployed
            else []
        )

    @property
    def constructor_calldata(self) -> List[Any]:
        return self.custom_constructor_calldata or super().constructor_calldata

    def sign_transaction(self, txn: TransactionAPI, **signer_options) -> Optional[TransactionAPI]:
        if not isinstance(txn, AccountTransaction):
            raise StarknetAccountsError(
                f"This account can only sign Starknet transactions (received={type(txn)}."
            )

        # NOTE: 'v' is not used
        signer = self._create_signer(to_int(self.private_key))
        stark_txn = txn.as_starknet_object()
        sign_result = signer.sign_transaction(stark_txn)
        return self.handle_signature(sign_result, txn)

    def sign_message(  # type: ignore[override]
        self, msg: StarknetSignableMessage
    ) -> Optional[ECSignature]:
        msg = StarknetSignableMessage(message=msg)
        signature = message_signature(msg.hash, to_int(self.private_key))
        return signature if self.check_signature(msg, signature) else None

    def add_deployment(self, network_name: str, contract_address: int, salt: int):
        if network_name != LOCAL_NETWORK_NAME:
            raise ValueError("Can only use development accounts on local network.")

        self.contract_address = self.provider.network.ecosystem.decode_address(contract_address)
        self.custom_salt = salt


class StarknetKeyfileAccount(BaseStarknetAccount):
    key_file_path: Path
    locked: bool = True
    __autosign: bool = False
    __cached_key: Optional[int] = None
    __cached_passphrase: Optional[str] = None

    @classmethod
    def from_file(cls, path: Path):
        account_data = json.loads(path.read_text())
        salt = account_data.get("salt")
        if not salt:
            salt = ContractAddressSalt.get_random_value()
            account_data = {**account_data, "salt": salt}
            path.unlink()
            path.write_text(json.dumps(account_data))

        return cls(key_file_path=path, salt=salt)

    @classmethod
    def _from_import(cls, new_path: Path, **kwargs) -> "StarknetKeyfileAccount":
        is_local = kwargs.pop("is_local", False)
        allow_local_file_store = kwargs.pop("allow_local_file_store", False)
        get_pass = kwargs.pop("get_pass")

        if not allow_local_file_store and is_local:
            # NOTE: To create a keyfile account on local networks, use `allow_local_filestore`.
            # Else, it uses a StarknetDevelopmentAccount and no passphrase is necessary.
            passphrase = None

        else:
            passphrase = get_pass()

        kwargs["passphrase"] = passphrase
        new_account = cls(key_file_path=new_path)
        new_account.write(**kwargs)
        return new_account

    @property
    def address(self) -> AddressType:
        if not self.network_manager.active_provider:
            return self.default_address

        network_name = self.provider.network.name
        deployment = self.get_deployment(network_name)
        if deployment:
            # For deployment for this network.
            # (may be different than what is calculated, depending on salt)
            return deployment.contract_address

        # Not yet deployed.
        return self.default_address

    @property
    def alias(self) -> Optional[str]:
        return self.key_file_path.stem

    @cached_property
    def class_hash(self) -> int:
        return self.account_data.get("class_hash", OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH)

    @cached_property
    def constructor_calldata(self) -> List[Any]:
        return self.account_data.get("constructor_calldata") or super().constructor_calldata

    @cached_property
    def salt(self) -> int:
        if "salt" in self.account_data:
            return self.account_data["salt"]

        # May only get here on outdated accounts.
        return ContractAddressSalt.get_random_value()

    @property
    def public_key(self) -> str:
        if "public_key" not in self.account_data:
            # Migrate keyfile now.
            private_key, passphrase = self.__get_private_key()
            key_pair = create_keypair(private_key)
            self.write(
                passphrase=passphrase,
                public_key=key_pair.public_key,
                private_key=key_pair.private_key,
            )

        return to_hex(self.account_data["public_key"])

    @property
    def nonce(self) -> int:
        return super().nonce if self.deployed else 0

    def sign_transaction(
        self, txn: TransactionAPI, **signer_optins: Any
    ) -> Optional[TransactionAPI]:
        if not isinstance(txn, AccountTransaction):
            raise StarknetAccountsError(
                f"This account can only sign Starknet transactions (received={type(txn)}."
            )

        if not self.__autosign and not self._prompt_to_sign(txn):
            raise SignatureError("The transaction was not signed.")

        # NOTE: 'v' is not used
        private_key, _ = self.__get_private_key()
        signer = self._create_signer(private_key)
        stark_txn = txn.as_starknet_object()
        sign_result = signer.sign_transaction(stark_txn)
        return self.handle_signature(sign_result, txn)

    def _prompt_to_sign(self, signable: Union[TransactionAPI, StarknetSignableMessage]) -> bool:
        return click.confirm(f"{signable}\n\nSign: ")

    def sign_message(  # type: ignore[override]
        self, msg: StarknetSignableMessage
    ) -> Optional[ECSignature]:
        msg = StarknetSignableMessage(message=msg)

        if not self.__autosign and not self._prompt_to_sign(msg):
            raise SignatureError("The message was not signed.")

        private_key, _ = self.__get_private_key()
        signature = message_signature(msg.hash, private_key)
        return signature if self.check_signature(msg, signature) else None

    @property
    def deployments(self) -> List[StarknetAccountDeployment]:
        deployments = self.account_data.get("deployments", [])

        # Add salt if missing (migration)
        for deployment in deployments:
            if (
                "salt" not in deployment
                and to_int(deployment["contract_address"]) == self.default_address_int
            ):
                deployment["salt"] = self.salt

        return [StarknetAccountDeployment(**d) for d in deployments]

    @property
    def deployed(self, network_name: Optional[str] = None) -> bool:
        network_name = network_name or self.provider.network.name
        network_deployments = [d for d in self.deployments if d.network_name == network_name]
        return len(network_deployments) > 0

    def prepare_transaction(self, txn: TransactionAPI) -> TransactionAPI:
        txn = self._prepare_transaction(txn)
        if not isinstance(txn, StarknetTransaction):
            raise TypeError("Can only prepare Starknet transactions.")

        if not txn.max_fee:
            if txn.signature is None:
                # Autosign has to quietly be enabled because because we have
                # to sign the txn twice - once before fee estimation and once after.
                # To the user, it only feels like a single sign of the latter.
                logger.debug("Fee-estimation related autosign enabled temporarily.")
                original_value = self.__autosign
                self.__autosign = True
                signed_txn = self.sign_transaction(txn)
                if signed_txn is not None:
                    signed_txn = cast(TransactionAPI, signed_txn)
                self.__autosign = original_value

            txn.max_fee = ceil(self.get_fee_estimate(txn) * FEE_MARGIN_OF_ESTIMATION)

        # Only sign the transaction if not aborting.
        # This is the real and final signature.
        signed_txn = self.sign_transaction(txn)
        if signed_txn is not None:
            return cast(TransactionAPI, signed_txn)
        return txn

    def write(
        self,
        passphrase: Optional[str] = None,
        new_passphrase: Optional[str] = None,
        public_key: Optional[int] = None,
        private_key: Optional[int] = None,
        class_hash: Optional[int] = None,
        deployments: Optional[List[Union[StarknetAccountDeployment]]] = None,
        salt: Optional[int] = None,
        constructor_calldata: Optional[List[Any]] = None,
        leave_unlocked: Optional[bool] = None,
    ):
        if not private_key:
            # Will either prompt or use cached if unlocked.
            private_key, passphrase = self.__get_private_key(
                passphrase=passphrase, leave_unlocked=leave_unlocked
            )

        passphrase_to_use = (
            new_passphrase
            if new_passphrase is not None
            else self.__get_passphrase(passphrase=passphrase)
        )

        key_file_data = self.__encrypt_key_file(
            passphrase_to_use, private_key=private_key, leave_unlocked=leave_unlocked
        )
        account_data = {**self.account_data}
        if public_key or "public_key" not in account_data:
            # Real public key to use is different than the one for the keyfile.
            public_key = public_key or create_keypair(private_key).public_key
            account_data["public_key"] = public_key

        if deployments:
            # Add deployments
            deployments_to_save: List[Dict] = []
            for deployment in deployments:
                if any([d == deployment for d in deployments_to_save]):
                    # Already known.
                    continue

                deployments_to_save.append(deployment.dict())

            account_data["deployments"] = deployments_to_save

        if class_hash:
            account_data["class_hash"] = class_hash
        if salt:
            account_data["salt"] = salt

        data = {**key_file_data, APP_KEY_FILE_KEY: account_data}
        self.key_file_path.write_text(json.dumps(data))

    @property
    def keyfile_data(self) -> Dict:
        if self.key_file_path.is_file():
            return json.loads(self.key_file_path.read_text())

        return {}

    @property
    def account_data(self) -> Dict:
        return self.keyfile_data.get(APP_KEY_FILE_KEY, {})

    def delete(
        self,
        address: Optional[Union[AddressType, int]] = None,
        networks: Optional[Union[str, List[str]]] = None,
        leave_unlocked: Optional[bool] = None,
    ):
        if not self.key_file_path.is_file():
            logger.warning(f"Keyfile for account '{self.alias}' already deleted.")
            return

        passphrase = click.prompt(
            f"Enter passphrase to delete '{self.alias}'",
            hide_input=True,
            default="",  # Allow for empty passphrases.
        )
        self.__decrypt_key_file(passphrase)
        deployments_at_start = len(self.deployments)
        if not networks and not address:
            remaining_deployments: List[StarknetAccountDeployment] = []

        else:
            address = self.address_int if address is None else to_int(address)
            networks = None if networks is None else [_clean_network_name(n) for n in networks]

            def deployment_filter(deployment: StarknetAccountDeployment) -> bool:
                deploy_address = to_int(deployment.contract_address)
                if networks and not address:
                    return deployment.network_name in networks

                elif address and not networks:
                    return deploy_address == address

                return deploy_address == address and deployment.network_name in (networks or [])

            remaining_deployments = [
                x for x in self.deployments if x not in filter(deployment_filter, self.deployments)
            ]

        if remaining_deployments and len(remaining_deployments) < deployments_at_start:
            self.write(
                passphrase=passphrase,
                deployments=remaining_deployments,
                leave_unlocked=leave_unlocked,
            )

        elif remaining_deployments:
            err_msg = f"Deletion failed. Deployment(s) not found (alias={self.alias}"
            if address:
                err_msg = f"{err_msg}, address={address}"
            if networks:
                net_str = ",".join(networks)
                err_msg = f"{err_msg}, networks={net_str}"

            raise StarknetAccountsError(f"{err_msg})")

        elif click.confirm(f"Completely delete local key for account '{self.address}'?"):
            # Delete entire account JSON if no more deployments.
            # The user has to agree to an additional prompt since this may be very destructive.
            self.key_file_path.unlink()

    def change_password(self, leave_unlocked: Optional[bool] = None):
        # NOTE: User must enter passphrase even if unlocked.
        original_passphrase = self._get_passphrase_from_prompt("Enter original passphrase")
        private_key, _ = self.__get_private_key(
            passphrase=original_passphrase, leave_unlocked=leave_unlocked
        )
        new_passphrase = self._get_passphrase_from_prompt("Enter new passphrase")
        self.write(
            passphrase=original_passphrase,
            new_passphrase=new_passphrase,
            private_key=private_key,
        )

    def add_deployment(
        self,
        network_name: str,
        contract_address: int,
        salt: int,
        leave_unlocked: Optional[bool] = None,
    ):
        if any([d == f"{network_name}:{contract_address}" for d in self.deployments]):
            logger.warning("Deployment already added.")
            return

        new_deployment = StarknetAccountDeployment(
            network_name=network_name, contract_address=contract_address, salt=salt
        )
        deployments = [*self.deployments, new_deployment]
        self.write(deployments=deployments, leave_unlocked=False)

    def unlock(self, prompt: Optional[str] = None, passphrase: Optional[str] = None):
        if not self.__cached_key or not self.__cached_passphrase:
            # Sets cached keys.
            self.__get_private_key(prompt=prompt, passphrase=passphrase, leave_unlocked=True)

        self.locked = False

    def set_autosign(self, enabled: bool, passphrase: Optional[str] = None):
        if enabled:
            self.unlock(passphrase=passphrase)
            logger.warning("Danger! This account will now sign any transaction its given.")
        else:
            self.lock()

        self.__autosign = enabled

    def lock(self):
        self.locked = True
        self.__cached_key = None
        self.__cached_passphrase = None

    def get_deployment(self, network_name: str) -> Optional[StarknetAccountDeployment]:
        # NOTE: d is not None check only because mypy is confused
        return next(
            filter(lambda d: d is not None and d.network_name in network_name, self.deployments),
            None,
        )

    def __get_private_key(
        self,
        prompt: Optional[str] = None,
        passphrase: Optional[str] = None,
        leave_unlocked: Optional[bool] = None,
    ) -> Tuple[int, Optional[str]]:
        if self.__cached_key is not None:
            if not self.locked:
                click.echo(f"Using cached key for '{self.alias}'")
                return self.__cached_key, self.__cached_passphrase
            else:
                # Only use the cached private key if unlocked.
                self.__cached_key = None
                self.__cached_passphrase = None

        passphrase = self.__get_passphrase(prompt=prompt, passphrase=passphrase)
        if self.key_file_path.is_file():
            key_hex_str = self.__decrypt_key_file(passphrase).hex()
            private_key = to_int(key_hex_str)
        else:
            # Should only happen if `.ape/starknet` folder corrupted.
            raise StarknetAccountsError(
                f"Keyfile for account '{self.alias}' missing. "
                "Either replace or use the `delete` command to get rid of this account."
            )

        self.__cached_key = private_key
        if passphrase is not None:
            self.__cached_passphrase = passphrase

        if self.locked:
            self.locked = (
                not click.confirm(f"Leave '{self.alias}' unlocked?")
                if leave_unlocked is None
                else leave_unlocked
            )

        return private_key, passphrase

    def __get_passphrase(
        self, prompt: Optional[str] = None, passphrase: Optional[str] = None
    ) -> str:
        passphrase = passphrase if passphrase is not None else self.__cached_passphrase
        return (
            passphrase
            if passphrase is not None
            else self._get_passphrase_from_prompt(message=prompt)
        )

    def _get_passphrase_from_prompt(self, message: Optional[str] = None) -> str:
        message = message or f"Enter passphrase to unlock '{self.alias}'"
        return click.prompt(
            message,
            hide_input=True,
            default="",  # Just in case there's no passphrase
            show_choices=False,
        )

    def __encrypt_key_file(
        self,
        passphrase: str,
        private_key: Optional[int] = None,
        leave_unlocked: Optional[bool] = None,
    ) -> Dict:
        private_key = (
            self.__get_private_key(passphrase=passphrase, leave_unlocked=leave_unlocked)[0]
            if private_key is None
            else private_key
        )
        key_str = pad_hex_str(HexBytes(private_key).hex())
        passphrase_bytes = text_if_str(to_bytes, passphrase)
        return create_keyfile_json(HexBytes(key_str), passphrase_bytes, kdf="scrypt")

    def __decrypt_key_file(self, passphrase: str) -> HexBytes:
        key_file_dict = json.loads(self.key_file_path.read_text())
        password_bytes = text_if_str(to_bytes, passphrase)
        decoded_json = decode_keyfile_json(key_file_dict, password_bytes)
        return HexBytes(decoded_json)


def _clean_network_name(network: str) -> str:
    for net in ("local", "mainnet", "testnet2", "testnet"):
        if net in network:
            return net

    if "goerli" in network:
        return "testnet"

    return network


def _create_key_file_app_data(deployments: List[Dict[str, str]]) -> Dict:
    return {APP_KEY_FILE_KEY: {"version": APP_KEY_FILE_VERSION, "deployments": deployments}}


__all__ = [
    "StarknetAccountContainer",
    "StarknetKeyfileAccount",
]
