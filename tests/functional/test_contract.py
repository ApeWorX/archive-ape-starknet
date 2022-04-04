import pytest


@pytest.fixture(scope="module")
def my_contract_type(project):
    return project.MyContract


@pytest.fixture(scope="module")
def my_contract(my_contract_type):
    return my_contract_type.deploy()


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


def test_contract_signed_transactions(my_contract, account):
    initial_amount = my_contract.get_balance()
    increase_amount = 234

    signature = account.sign_message(increase_amount)
    my_contract.increase_balance_signed(account.address, increase_amount, signature)

    actual = my_contract.get_balance()
    expected = initial_amount + increase_amount
    assert actual == expected
