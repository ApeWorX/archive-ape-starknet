import pytest
from ape import Contract
from ape.contracts import ContractInstance
from ape.exceptions import ContractLogicError, OutOfGasError


@pytest.fixture(scope="module", autouse=True)
def connection(provider):
    yield


def test_deploy(project):
    assert project.MyContract, "Unable to access contract when needing to compile"

    contract = project.MyContract
    assert contract, "Unable to access contract when not needing to compile"

    deployment = contract.deploy()
    assert deployment


def test_declare_then_deploy(account, chain, project, provider, factory_contract_container):
    # Declare contract type. The result should contain a 'class_hash'.
    declaration = provider.declare(project.MyContract)
    assert declaration.class_hash

    # Deploy a ContractInstance from the declaration.
    contract = declaration.deploy()
    assert isinstance(contract, ContractInstance)

    # Ensure can interact with deployed contract from declaration.
    contract.initialize(sender=account)
    balance_pre_call = contract.get_balance(account)
    contract.increase_balance(account, 9, sender=account)
    assert contract.get_balance(account) == balance_pre_call + 9

    # Ensure can use class_hash in factory contract
    factory = factory_contract_container.deploy(declaration.class_hash)
    receipt = factory.create_my_contract(sender=account)
    logs = list(receipt.decode_logs(factory.contract_deployed))
    new_contract_address = provider.starknet.decode_address(logs[0].contract_address)

    # # Ensure can interact with deployed contract from 'class_hash'.
    new_contract_instance = Contract(new_contract_address, contract_type=contract.contract_type)
    new_contract_instance.initialize(sender=account)
    balance_pre_call = new_contract_instance.get_balance(account)
    new_contract_instance.increase_balance(account, 9, sender=account)
    assert new_contract_instance.get_balance(account) == balance_pre_call + 9


def test_get_caller_address(contract, account, provider):
    expected = provider.starknet.encode_address(account.address)
    assert contract.get_caller(sender=account).return_value == expected


def test_validate_signature_on_chain(contract, account, initial_balance):
    # NOTE: This test validates the account signature but the transaction
    # is not directly sent from the account.
    increase_amount = 42 * 2**152

    signature = account.sign_message(increase_amount)
    contract.increase_balance_signed(
        account.public_key, account.address, increase_amount, signature
    )

    actual = contract.get_balance(account)
    expected = initial_balance + increase_amount
    assert actual == expected


def test_transact_from_account(contract, account, initial_balance):
    increase_amount = 123456
    receipt = contract.increase_balance(account, increase_amount, sender=account)
    actual_from_receipt = receipt.return_value
    actual_from_call = contract.get_balance(account)
    expected = initial_balance + increase_amount
    assert actual_from_receipt == actual_from_call == expected


def test_contracts_as_arguments(contract, account):
    initial_balance = contract.get_balance(contract)
    increase_amount = 123456
    receipt = contract.increase_balance(contract, increase_amount, sender=account)
    actual_from_receipt = receipt.return_value
    actual_from_call = contract.get_balance(contract)
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

    # Re-initialize (re-store state)
    contract.initialize()


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
    assert receipt.returndata == ["0x3", "0x1", "0x2", "0x3"]
    assert receipt.return_value == [1, 2, 3]


def test_external_call_array_outputs_from_account(contract, account):
    receipt = contract.get_array(sender=account)
    assert receipt.returndata == ["0x4", "0x3", "0x1", "0x2", "0x3"]
    assert receipt.return_value == [1, 2, 3]


def test_view_call_array_outputs(contract, account):
    array = contract.view_array()
    assert array == [1, 2, 3]


def test_unable_to_afford_transaction(contract, account, provider):
    with pytest.raises(OutOfGasError):
        contract.increase_balance(account.address, 1, sender=account, max_fee=1)
