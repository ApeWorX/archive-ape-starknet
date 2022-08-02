import pytest

AMOUNT_0 = 10
AMOUNT_1 = 2**128 + 42


@pytest.fixture
def receipt(token_contract, account, second_account):
    return token_contract.fire_events(second_account.address, AMOUNT_0, AMOUNT_1, sender=account)


def test_decode_logs(receipt, token_contract, account, second_account):
    transfer_logs = list(receipt.decode_logs(token_contract.Transfer))
    assert len(transfer_logs) == 1
    log = transfer_logs[0]
    assert log.from_ == int(account.address, 16)
    assert log.to == int(second_account.address, 16)
    assert log.value == AMOUNT_0

    mint_logs = list(receipt.decode_logs(token_contract.Mint))
    assert len(mint_logs) == 1
    log = mint_logs[0]
    assert log.sender == int(account.address, 16)
    assert log.amount0 == AMOUNT_0
    assert log.amount1 == AMOUNT_1
    assert log.to == int(second_account.address, 16)


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
