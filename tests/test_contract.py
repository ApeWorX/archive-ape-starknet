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


def test_contract_transactions(my_contract, provider):
    my_contract.increase_balance(100)
    assert my_contract.get_balance() == 100
