import pytest
from ape.api.networks import LOCAL_NETWORK_NAME
from click.testing import CliRunner
from hexbytes import HexBytes

from ape_starknet.accounts import DEVNET_CONTRACT_SALT, StarknetAccountDeployment
from ape_starknet.utils import OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH, is_hex_address


@pytest.fixture
def give_input():
    def fn(msg):
        return CliRunner().isolation(input=msg)

    return fn


@pytest.fixture
def devnet_keyfile_account(account_container, account, password, give_input):
    deployments = [
        StarknetAccountDeployment(
            contract_address=account.address, network_name="testnet", salt=DEVNET_CONTRACT_SALT
        )
    ]

    with give_input(f"{password}\n{password}\n"):
        return account_container.import_account(
            "__DEV_AS_KEYFILE_ACCOUNT__",
            OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH,
            account.private_key,
            deployments=deployments,
            salt=DEVNET_CONTRACT_SALT,
        )


@pytest.fixture
def txn(devnet_keyfile_account):
    return devnet_keyfile_account.get_deploy_account_txn()


def test_public_key(key_file_account, public_key):
    actual = key_file_account.public_key
    assert int(actual, 16) == public_key


def test_address(account):
    assert is_hex_address(account.address)


def test_account_container_contains(account, second_account, key_file_account, account_container):
    assert account.address in account_container
    assert second_account.address in account_container
    assert key_file_account.address in account_container


CASE_NAME_TO_LAMBDA = {
    "address_str": lambda a, _: a.address,
    "address_int": lambda a, e: e.encode_address(a.address),
    "public_key_str": lambda a, _: a.public_key,
    "public_key_int": lambda a, e: e.encode_address(a.public_key),
}


@pytest.mark.parametrize("case", [x for x in CASE_NAME_TO_LAMBDA.keys()])
def test_access_account_by_str_address(account, account_container, starknet, case):
    get_address = CASE_NAME_TO_LAMBDA[case]
    address = get_address(account, starknet)
    assert account_container[address] == account
    assert address in account_container


def test_balance(account, ephemeral_account, tokens):
    balance = account.balance
    assert isinstance(balance, int)
    assert balance > 0

    balance = ephemeral_account.balance
    assert isinstance(balance, int)
    assert balance > 0

    # Clear caches and make sure still works (uses RPC)
    del tokens.balance_cache[account.address_int]
    del tokens.balance_cache[ephemeral_account.address_int]

    balance = account.balance
    assert isinstance(balance, int)
    assert balance > 0

    balance = ephemeral_account.balance
    assert isinstance(balance, int)
    assert balance > 0


def test_can_access_devnet_accounts(account, second_account, chain):
    assert chain.contracts[account.address] == account.contract_type
    assert chain.contracts[second_account.address] == second_account.contract_type


def test_import_with_passphrase(account_container, account, give_input):
    alias = "__TEST_IMPORT_WITH_PASSPHRASE__"
    deployment = StarknetAccountDeployment(
        contract_address=account.address, network_name=LOCAL_NETWORK_NAME, salt=DEVNET_CONTRACT_SALT
    )

    with give_input("p@55W0rd\np@55W0rd\n"):
        account_container.import_account(
            alias,
            OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH,
            account.private_key,
            deployments=[deployment],
        )
    new_account = account_container.load(alias)
    assert new_account.address == account.address


def test_transfer(account, second_account):
    initial_account_balance = account.balance
    initial_second_account_balance = second_account.balance
    receipt = account.transfer(second_account, 10)
    total_cost = receipt.total_fees_paid + 10
    assert second_account.balance == initial_second_account_balance + 10
    assert account.balance == initial_account_balance - total_cost


@pytest.mark.parametrize("msg", (5, [5, 6], b"5", HexBytes(122)))
def test_sign_message(msg, key_file_account, password):
    key_file_account.set_autosign(True, passphrase=password)
    assert key_file_account.sign_message(msg)
    key_file_account.set_autosign(False)


def test_unlock_with_passphrase_and_sign_message(
    in_starknet_testnet, give_input, devnet_keyfile_account, password
):
    devnet_keyfile_account.unlock(passphrase=password)
    with give_input("y\n"):
        devnet_keyfile_account.sign_message([1, 2, 3])


def test_unlock_from_prompt_and_sign_message(
    in_starknet_testnet, give_input, devnet_keyfile_account, password
):
    with give_input(f"{password}\n"):
        devnet_keyfile_account.unlock()

    with give_input("y\n"):
        devnet_keyfile_account.sign_message([1, 2, 3])


def test_unlock_with_passphrase_and_sign_transaction(
    in_starknet_testnet, give_input, devnet_keyfile_account, password, txn
):
    devnet_keyfile_account.unlock(passphrase=password)
    with give_input("y\n"):
        devnet_keyfile_account.sign_transaction(txn)


def test_unlock_from_prompt_and_sign_transaction(
    in_starknet_testnet, give_input, devnet_keyfile_account, password, txn
):
    with give_input(f"{password}\n"):
        devnet_keyfile_account.unlock()

    with give_input("y\n"):
        devnet_keyfile_account.sign_transaction(txn)


def test_set_autosign(in_starknet_testnet, give_input, devnet_keyfile_account, password, txn):
    with give_input(f"{password}\n"):
        devnet_keyfile_account.set_autosign(True)

    devnet_keyfile_account.sign_transaction(txn)

    # Disable and verify we have to sign again
    devnet_keyfile_account.set_autosign(False)
    with give_input(f"y\n{password}\n"):
        devnet_keyfile_account.sign_transaction(txn)


def test_set_autosign_and_provide_passphrase(
    in_starknet_testnet, give_input, devnet_keyfile_account, password, txn
):
    devnet_keyfile_account.set_autosign(True, passphrase=password)
    devnet_keyfile_account.sign_transaction(txn)

    # Disable and verify we have to sign again
    devnet_keyfile_account.set_autosign(False)
    with give_input(f"y\n{password}\n"):
        devnet_keyfile_account.sign_transaction(txn)


def test_accounts_devnet_accounts_are_still_available_on_ethereum(account_container, networks):
    assert account_container.test_accounts

    with networks.ethereum.local.use_provider("test"):
        # Accounts are still found even though devnet is not the active provider.
        assert account_container.test_accounts

    assert account_container.test_accounts
