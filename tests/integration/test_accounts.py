import random
import re
from typing import List, Tuple, Union

import pytest
from eth_utils import to_hex
from starknet_py.utils.crypto.facade import message_signature
from starkware.crypto.signature.signature import EC_ORDER

from ape_starknet.types import StarknetSignableMessage
from ape_starknet.utils import get_random_private_key, to_int

from .conftest import ApeStarknetCliRunner


def get_random_alias() -> str:
    return "".join(random.choice(["a", "b", "c", "d", "e", "f"]) for _ in range(6))


TESTNET_KEY = "Contract address (testnet)"
TESTNET2_KEY = "Contract address (testnet2)"
MAINNET_KEY = "Contract address (mainnet)"


class ListOutputSection:
    def __init__(self, alias: str, lines: List[str]):
        self.alias = alias
        self.lines = lines

    def __iter__(self):
        yield from self.lines

    def __str__(self):
        return "\n".join(self.lines)

    def __repr__(self):
        return str(self) if bool(self) else "<no section>"

    def __bool__(self):
        return len(self.lines) > 0

    def __contains__(self, item: Union[Tuple, str]) -> bool:
        if isinstance(item, str):
            return any([item in line for line in self.lines])

        key, value = item
        key = key.replace("(", r"\(").replace(")", r"\)")
        pattern = re.compile(rf"{key} +- {value}")
        return any([pattern.match(x) for x in self.lines])

    def fail_msg(self, key: str, value: str) -> str:
        return f"{self.alias} with '{key} - {value}' not found. Full output: {self}"


class ListOutputWrapper:
    def __init__(self, output: str):
        self.output = output

    @property
    def lines(self) -> List[str]:
        return self.output.splitlines()

    def __iter__(self):
        yield from self.lines

    def __repr__(self):
        return self.output

    def get_section(self, alias: str) -> ListOutputSection:
        section: List[str] = []
        for index, line in enumerate(self.lines):
            if alias not in line and not section:
                # Haven't found start of the section yet.
                continue

            part = line.strip()
            if section and not part:
                # End found - next section started.
                return ListOutputSection(alias, section)

            section.append(part)

        # End found - no more output.
        return ListOutputSection(alias, section)


@pytest.fixture(scope="module")
def accounts_runner(ape_cli):
    class AccountsCliRunner(ApeStarknetCliRunner):
        def __init__(self):
            super().__init__(ape_cli, ["starknet", "accounts"])

        def invoke_list(self, *args, **kwargs) -> ListOutputWrapper:
            output = self.invoke("list", *args, **kwargs)
            return ListOutputWrapper(output)

    return AccountsCliRunner()


@pytest.fixture(scope="module")
def root_accounts_runner(ape_cli):
    return ApeStarknetCliRunner(ape_cli, ["accounts"])


def test_create_then_list_then_deploy(accounts_runner, account_container, password):
    """
    * Create a new acount key-pair (using OZ class hash by default).
    * Deploy an instance of the account.
    """

    # Create the keypair locally, without deployments.
    alias = get_random_alias()
    user_input = [password, password]  # ["123", confirm]
    output = accounts_runner.invoke("create", alias, input=user_input)

    # Ensure output used correct prompt.
    assert output.splitlines()[1].startswith(f"Create passphrase to encrypt account '{alias}'")

    # Ensure the account was created.
    assert f"Created account key-pair for alias '{alias}'" in output
    account = account_container.load(alias)
    assert not account.deployments

    # Ensure the alias shows in the list command as "not deployed".
    output = accounts_runner.invoke_list()
    section = output.get_section(alias)
    key = "Contract address (not deployed)"
    value = account.address
    assert (key, value) in section, section.fail_msg(key, value)

    # Deploy and verify.
    user_input = [password, "y"]  # ["123", yes to sign].
    output = accounts_runner.invoke("deploy", alias, "--funder", "0", input=user_input)
    assert "Account successfully deployed to " in output
    assert account.deployments


def test_create_then_use_then_delete_account_with_empty_passphrase(
    accounts_runner, account_container
):
    alias = get_random_alias()
    output = accounts_runner.invoke("create", alias, input=["", ""])
    assert "SUCCESS" in output

    account = account_container.load(alias)

    # Input meaning: ENTER (no pass).
    with accounts_runner.runner.isolation(input="\n"):
        account.unlock()

    output = accounts_runner.invoke("delete", alias, input=["", "y"])
    assert "SUCCESS" in output


@pytest.mark.parametrize(
    "class_hash",
    (
        "0x025ec026985a3bf9d0cc1fe17326b245dfdc3ff89b8fde106542a3ea56c5a918",
        str(int("0x025ec026985a3bf9d0cc1fe17326b245dfdc3ff89b8fde106542a3ea56c5a918", 16)),
    ),
)
def test_create_with_class_hash(accounts_runner, account_container, class_hash, password):
    """
    Create a keypair with a custom class hash.
    """

    # Create the account with a custom class hash.
    alias = get_random_alias()
    user_input = [password, password]  # ["123", confirm]
    output = accounts_runner.invoke("create", alias, "--class-hash", class_hash, input=user_input)
    assert f"Created account key-pair for alias '{alias}'" in output
    account = account_container.load(alias)
    assert account.class_hash == to_int(class_hash)

    # Ensure the custom class hash gets displayed.
    output = accounts_runner.invoke_list()
    section = output.get_section(alias)
    key = "Class hash"
    value = to_hex(to_int(class_hash))
    assert (key, value) in section, section.fail_msg(key, value)


def test_list(accounts_runner, key_file_account, contract_address):
    """
    Ensure the list command works in a basic sense for an account with a single
    deployment.
    """
    output = accounts_runner.invoke_list()
    section = output.get_section(key_file_account.alias)
    alias = ("Alias", key_file_account.alias)
    public_key = ("Public key", key_file_account.public_key)
    class_hash = ("Class hash", to_hex(key_file_account.class_hash))
    deployment = (TESTNET_KEY, contract_address)
    assert alias in section, section.fail_msg(*alias)
    assert public_key in section, section.fail_msg(*public_key)
    assert class_hash in section, section.fail_msg(*class_hash)
    assert deployment in section, section.fail_msg(*deployment)


def test_import_then_delete_deployment(
    accounts_runner, key_file_account, password, contract_address
):
    """
    * Start with an account with single deployments on testnet
    * Import deployments to testnet2 and mainnet
    * Delete deployments testnet2 and mainnet

    The account never completely goes away because it has multiple deployments.
    """

    # Import the deployments.
    accounts_runner.invoke(
        "import",
        key_file_account.alias,
        "--network",
        "testnet2,mainnet",
        "--address",
        contract_address,
        "--class-hash",
        key_file_account.class_hash,
        input=password,
    )
    actual_0 = (TESTNET_KEY, contract_address)
    actual_1 = (TESTNET2_KEY, contract_address)
    actual_2 = (MAINNET_KEY, contract_address)

    # Ensure new deployments show up in list output.
    output = accounts_runner.invoke_list()
    section = output.get_section(key_file_account.alias)
    assert actual_0 in section, section.fail_msg(*actual_0)
    assert actual_1 in section, section.fail_msg(*actual_1)
    assert actual_2 in section, section.fail_msg(*actual_2)

    # Delete the new deployments.
    user_input = [password]  # ["123"]
    output = accounts_runner.invoke(
        "delete",
        key_file_account.alias,
        "--network",
        "mainnet,testnet2",
        "--address",
        contract_address,
        input=user_input,
    )
    assert (
        f"Account '{key_file_account.alias}' deployments on network 'mainnet,testnet2' deleted"
    ) in output

    # Ensure testnet deployment was deleted but not testnet2.
    output = accounts_runner.invoke_list()
    section = output.get_section(key_file_account.alias)
    assert actual_0 in section, section.fail_msg(*actual_0)
    assert actual_1 not in section, f"{TESTNET2_KEY} still present."


def test_import_then_delete_account(
    accounts_runner,
    key_file_account,
    account_container,
    password,
):
    # Import a new account (no deployments or keys set at all for this alias).
    alias = get_random_alias()

    # [privkey, new pass, confirm pass]
    user_input = [str(get_random_private_key()), password, password]

    accounts_runner.invoke(
        "import",
        alias,
        "--network",
        "testnet",
        "--address",
        key_file_account.address,
        "--class-hash",
        key_file_account.class_hash,
        input=user_input,
    )

    # Verify it shows up in list output.
    output = accounts_runner.invoke_list()
    section = output.get_section(alias)
    assert (TESTNET_KEY, key_file_account.address) in section, section.fail_msg(
        key_file_account.address
    )

    # Delete the account.
    user_input = [password, "y"]  # ["123", yes delete entire thing]
    accounts_runner.invoke("delete", alias, input=user_input)

    # Verify it does not show in the list output.
    output = accounts_runner.invoke_list()
    section = output.get_section(alias)
    assert not section


def test_import_invalid_private_key(accounts_runner, key_file_account):
    # Import a new account (no deployments or keys set at all for this alias).
    alias = get_random_alias()
    user_input = ["This is not a valid private key"]
    output = accounts_runner.invoke(
        "import",
        alias,
        "--network",
        "testnet",
        "--address",
        key_file_account.address,
        "--class-hash",
        key_file_account.class_hash,
        input=user_input,
        ensure_successful=False,
    )
    assert "Invalid private key. Expecting numeric value." in output


@pytest.mark.parametrize("private_key", (0, EC_ORDER))
def test_import_private_key_out_of_range(accounts_runner, key_file_account, private_key):
    # Import a new account (no deployments or keys set at all for this alias).
    alias = get_random_alias()
    user_input = [private_key]
    output = accounts_runner.invoke(
        "import",
        alias,
        "--network",
        "testnet",
        "--address",
        key_file_account.address,
        "--class-hash",
        key_file_account.class_hash,
        input=user_input,
        ensure_successful=False,
    )
    assert "Private key not in range [1, EC_ORDER)." in output


def test_core_accounts_list_all(root_accounts_runner, key_file_account, existing_key_file_alias):
    """
    Ensure the normal `ape accounts list --all` command works.
    """

    assert existing_key_file_alias in root_accounts_runner.invoke("list", "--all")


def test_change_password(accounts_runner, key_file_account, password, existing_key_file_alias):
    """
    Changes the password and then changes it back.
    """

    new_password = "321"
    assert "SUCCESS" in accounts_runner.invoke(
        "change-password", existing_key_file_alias, input=[password, new_password, new_password]
    )
    assert "SUCCESS" in accounts_runner.invoke(
        "change-password", existing_key_file_alias, input=[new_password, password, password]
    )


def test_export(accounts_runner, key_file_account, password):
    output = accounts_runner.invoke("export", key_file_account.alias, input=[password])
    key_from_output = int(output.split(" private key: ")[-1].strip(" )\n"))

    # Sign a message using the exported private key.
    msg = StarknetSignableMessage(message="test test test")
    actual_signature = message_signature(msg.hash, key_from_output)

    # Sign the same message using the account.
    with accounts_runner.runner.isolation(f"y\n{password}\n"):
        expected_signature = key_file_account.sign_message(msg)

    # The signatures should be the same to prove exporting works.
    assert actual_signature == expected_signature
