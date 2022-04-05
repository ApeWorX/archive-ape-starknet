import pytest


@pytest.fixture(scope="module", autouse=True)
def connection(provider):
    yield


def test_deploy(project):
    assert project.MyContract, "Unable to access contract when needing to compile"

    contract = project.MyContract
    assert contract, "Unable to access contract when not needing to compile"

    deployment = contract.deploy()
    assert deployment


def test_contract_transactions(my_contract):
    initial_amount = my_contract.get_balance()
    increase_amount = 100

    my_contract.increase_balance(increase_amount)

    actual = my_contract.get_balance()
    expected = initial_amount + increase_amount
    assert actual == expected


def test_contract_transaction_handles_non_felt_arguments(my_contract, account, initial_balance):
    # NOTE: This test validates the account signature but the transaction
    # is not directly sent from the account. Both are valid use-cases!
    increase_amount = 234

    signature = account.sign_message(increase_amount)
    my_contract.increase_balance_signed(account.address, increase_amount, signature)

    actual = my_contract.get_balance()
    expected = initial_balance + increase_amount
    assert actual == expected


def test_signed_contract_transaction(my_contract, account, initial_balance):
    increase_amount = 123456
    my_contract.increase_balance(increase_amount, sender=account)

    actual = my_contract.get_balance()
    expected = initial_balance + increase_amount
    assert actual == expected
