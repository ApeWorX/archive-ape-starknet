import pytest
from ape.exceptions import AccountsError, ContractLogicError


@pytest.fixture(scope="module", autouse=True)
def connection(provider):
    yield


def test_deploy(project):
    assert project.MyContract, "Unable to access contract when needing to compile"

    contract = project.MyContract
    assert contract, "Unable to access contract when not needing to compile"

    deployment = contract.deploy()
    assert deployment


def test_contract_transaction_handles_non_felt_arguments(contract, account, initial_balance):
    # NOTE: This test validates the account signature but the transaction
    # is not directly sent from the account.
    increase_amount = 234

    signature = account.sign_message(increase_amount)
    contract.increase_balance_signed(account.address, increase_amount, signature)

    actual = contract.get_balance(account.address)
    expected = initial_balance + increase_amount
    assert actual == expected


def test_signed_contract_transaction(contract, account, initial_balance):
    increase_amount = 123456
    receipt = contract.increase_balance(account.address, increase_amount, sender=account)
    actual_from_receipt = receipt.return_value
    actual_from_call = contract.get_balance(account.address)
    expected = initial_balance + increase_amount
    assert actual_from_receipt == actual_from_call == expected


def test_unsigned_contract_transaction(contract, account, initial_balance):
    increase_amount = 123456
    receipt = contract.increase_balance(account.address, increase_amount)

    actual_from_receipt = receipt.return_value
    actual_from_call = contract.get_balance(account.address)
    expected = initial_balance + increase_amount
    assert actual_from_receipt == actual_from_call == expected


def test_decode_logs(contract, account, ecosystem):
    increase_amount = 9933
    receipt = contract.increase_balance(account.address, increase_amount, sender=account)
    logs = list(receipt.decode_logs(contract.balance_increased))
    assert len(logs) == 1
    assert logs[0].amount == increase_amount

    from_address = receipt.logs[0]["from_address"]
    log_sender_address = ecosystem.decode_address(from_address)
    assert log_sender_address == contract.address


def test_revert_message(contract):
    with pytest.raises(ContractLogicError) as err:
        # Already initialized from fixture
        contract.initialize()

    assert str(err.value) == "Already initialized"


def test_revert_no_message(contract, account):
    contract.reset()
    with pytest.raises(ContractLogicError) as err:
        contract.increase_balance(account.address, 123)

    assert "An ASSERT_EQ instruction failed" in str(err.value)


def test_array_inputs(contract, account):
    # This test makes sure we can pass python lists as arguments
    # to Cairo methods that accept arrays.
    # NOTE: Due to a limitation in ape, we have to include the array length argument.
    contract.store_sum(3, [1, 2, 3])
    actual = contract.get_last_sum()
    expected = 6
    assert actual == expected


def test_external_call_array_outputs(contract, account):
    receipt = contract.get_array()
    assert receipt.return_value == [1, 2, 3]


def test_external_call_array_outputs_from_account(contract, account):
    receipt = contract.get_array(sender=account)
    assert receipt.return_value == [1, 2, 3]


def test_view_call_array_outputs(contract, account):
    array = contract.view_array()
    assert array == [1, 2, 3]


def test_unable_to_afford_transaction(contract, account, provider):
    # This also indirectly tests `estimate_gas_cost()`.

    try:
        provider.default_gas_cost = 123321123321
        with pytest.raises(AccountsError) as err:
            contract.increase_balance(account.address, 1, sender=account)

        assert "Transfer value meets or exceeds account balance." in str(err.value)
    finally:
        provider.default_gas_cost = 0
