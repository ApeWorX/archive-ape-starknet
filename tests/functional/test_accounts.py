import pytest
from ape.api.networks import LOCAL_NETWORK_NAME
from click.testing import CliRunner
from starkware.cairo.lang.vm.cairo_runner import pedersen_hash

from ape_starknet.utils import is_hex_address

from ..conftest import PASSWORD


@pytest.fixture
def isolation():
    return CliRunner().isolation


@pytest.fixture
def devnet_keyfile_account(account_container, account):
    account_container.import_account(
        "__DEV_AS_KEYFILE_ACCOUNT__",
        "testnet",
        account.address,
        private_key=account.private_key,
        passphrase="123",
    )
    return account_container.load("__DEV_AS_KEYFILE_ACCOUNT__")


def test_public_keys(key_file_account, public_key):
    actual = key_file_account.public_key
    assert actual == public_key


def test_sign_message_using_key_file_account(key_file_account, password):
    assert key_file_account.sign_message(5, passphrase=password)


def test_address(account):
    assert is_hex_address(account.address)


def test_sign_message_and_check_signature(account):
    data = 500
    signature = account.sign_message(data)
    data_hash = pedersen_hash(data, 0)
    result = account.check_signature(data_hash, signature)
    assert result, "Failed to validate signature"


def test_sign_message_and_check_signature_using_deployed_account(ephemeral_account):
    data = 500
    signature = ephemeral_account.sign_message(data)
    data_hash = pedersen_hash(data, 0)
    result = ephemeral_account.check_signature(data_hash, signature)
    assert result, "Failed to validate signature"


def test_account_container_contains(account, second_account, key_file_account, account_container):
    assert account.address in account_container
    assert second_account.address in account_container
    assert key_file_account.address in account_container


@pytest.mark.parametrize(
    "get_address",
    [
        lambda a, _: a.address,
        lambda a, e: e.encode_address(a.address),
        lambda a, _: a.public_key,
        lambda a, e: e.encode_address(a.public_key),
    ],
)
def test_access_account_by_str_address(account, account_container, ecosystem, get_address):
    address = get_address(account, ecosystem)
    assert account_container[address] == account
    assert address in account_container


def test_balance(account):
    balance = account.balance
    assert isinstance(balance, int)
    assert account.balance > 0


def test_can_access_devnet_accounts(account, second_account, chain):
    assert chain.contracts[account.address] == account.get_contract_type()
    assert chain.contracts[second_account.address] == second_account.get_contract_type()


def test_import_with_passphrase(account_container, key_file_account):
    alias = "__TEST_IMPORT_WITH_PASSPHRASE__"
    account_container.import_account(
        alias,
        LOCAL_NETWORK_NAME,
        key_file_account.address,
        key_file_account._get_key(PASSWORD),
        passphrase="p@55W0rd",
    )
    new_account = account_container.load(alias)
    assert new_account.address == key_file_account.address


def test_transfer(account, second_account):
    initial_balance = second_account.balance
    account.transfer(second_account, 10)
    assert second_account.balance == initial_balance + 10


def test_unlock_with_passphrase_and_sign_message(isolation, devnet_keyfile_account):
    devnet_keyfile_account.unlock(passphrase="123")

    with isolation(input="y\n"):
        devnet_keyfile_account.sign_message([1, 2, 3])


def test_unlock_from_prompt_and_sign_message(isolation, devnet_keyfile_account):
    with isolation(input="123\n"):
        devnet_keyfile_account.unlock()

    with isolation(input="y\n"):
        devnet_keyfile_account.sign_message([1, 2, 3])


def test_unlock_with_passphrase_and_sign_transaction(isolation, devnet_keyfile_account, contract):
    devnet_keyfile_account.unlock(passphrase="123")

    with isolation(input="y\n"):
        contract.increase_balance(devnet_keyfile_account, 100, sender=devnet_keyfile_account)


def test_unlock_from_prompt_and_sign_transaction(isolation, devnet_keyfile_account, contract):
    with isolation(input="123\n"):
        devnet_keyfile_account.unlock()

    with isolation(input="y\n"):
        contract.increase_balance(devnet_keyfile_account, 100, sender=devnet_keyfile_account)


def test_set_autosign(isolation, devnet_keyfile_account, contract):
    with isolation(input="123\n"):
        devnet_keyfile_account.set_autosign(True)

    contract.increase_balance(devnet_keyfile_account, 100, sender=devnet_keyfile_account)

    # Disable and verify we have to sign again
    devnet_keyfile_account.set_autosign(False)
    with isolation(input="123\ny\n"):
        contract.increase_balance(devnet_keyfile_account, 100, sender=devnet_keyfile_account)


def test_set_autosign_and_provide_passphrase(isolation, devnet_keyfile_account, contract):
    devnet_keyfile_account.set_autosign(True, passphrase="123")
    contract.increase_balance(devnet_keyfile_account, 100, sender=devnet_keyfile_account)

    # Disable and verify we have to sign again
    devnet_keyfile_account.set_autosign(False)
    with isolation(input="123\ny\n"):
        contract.increase_balance(devnet_keyfile_account, 100, sender=devnet_keyfile_account)
