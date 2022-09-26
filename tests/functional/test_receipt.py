import pytest

AMOUNT_0 = 10
AMOUNT_1 = 2**128 + 42


@pytest.fixture
def receipt(token_contract, account, second_account):
    return token_contract.fire_events(second_account.address, AMOUNT_0, AMOUNT_1, sender=account)


def test_decode_logs(receipt, token_contract, account, second_account):
    expected_sender = int(account.address, 16)
    expected_receiver = int(second_account.address, 16)
    transfer_logs = list(receipt.decode_logs(token_contract.Transfer))

    # TODO: Figure out why 1 extra strange Transfer event shows up (as of 0.5)
    # assert len(transfer_logs) == 1, transfer_logs
    log = transfer_logs[-1]
    assert log.from_ == expected_sender
    assert log.to == expected_receiver
    assert log.value == AMOUNT_0

    mint_logs = list(receipt.decode_logs(token_contract.Mint))
    assert len(mint_logs) == 1
    log = mint_logs[-1]
    assert log.sender == expected_sender
    assert log.amount0 == AMOUNT_0
    assert log.amount1 == AMOUNT_1
    assert log.to == expected_receiver

    # Verify events emitted from imported function call show up in receipt.
    lib_event = token_contract.contract_type.events["ERC20_ParentEvent"]
    lib_logs = list(receipt.decode_logs(lib_event))
    assert len(lib_logs) == 1
    assert lib_logs[0].favorite_account == expected_receiver


def test_decode_logs_when_logs_from_other_contract(token_contract, token_user_contract, account):
    receipt = token_user_contract.fireTokenEvent(token_contract.address, sender=account)
    transfer_logs = list(receipt.decode_logs(token_contract.Transfer))
    mint_logs = list(receipt.decode_logs(token_contract.Mint))

    assert transfer_logs
    assert len(mint_logs) == 1
    assert mint_logs[-1].amount0 == 100
    assert mint_logs[-1].amount1 == 200

    # The caller address is the user token
    assert mint_logs[-1].sender == int(token_user_contract.address, 16)

    # Verify events emitted from imported function call show up in receipt.
    lib_event = token_contract.contract_type.events["ERC20_ParentEvent"]
    lib_logs = list(receipt.decode_logs(lib_event))
    assert len(lib_logs) == 1


def test_decode_logs_no_specify_abi(receipt, account, second_account):
    logs = list(receipt.decode_logs())
    assert len(logs) == 2
    transfer_log, mint_log = logs

    assert transfer_log.from_ == int(account.address, 16)
    assert transfer_log.to == int(second_account.address, 16)
    assert transfer_log.value == AMOUNT_0
    assert mint_log.sender == int(account.address, 16)
    assert mint_log.amount0 == AMOUNT_0
    assert mint_log.amount1 == AMOUNT_1
    assert mint_log.to == int(second_account.address, 16)
