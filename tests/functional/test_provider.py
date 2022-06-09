import time

import pytest
from starkware.starknet.public.abi import get_selector_from_name

from ape_starknet.exceptions import StarknetProviderError
from ape_starknet.utils import is_checksum_address


def test_get_nonce(provider, account, contract):
    initial_nonce = provider.get_nonce(account.address)

    # Transact to increase nonce
    contract.increase_balance(account.address, 123, sender=account)

    actual = provider.get_nonce(account.address)
    assert actual == initial_nonce + 1


def test_get_block(provider, contract):
    _ = contract  # Contract fixture used to increase blocks (since deploys happen)
    latest_block_0 = provider.get_block("latest")
    latest_block_1 = provider.get_block(-1)
    latest_block_2 = provider.get_block(latest_block_0.number)
    assert latest_block_0.hash == latest_block_1.hash == latest_block_2.hash


def test_get_negative_block_number(account, provider, contract):
    start_block = provider.get_block("latest").number
    for _ in range(3):
        # Mine 3 blocks
        contract.increase_balance(account.address, 12, sender=account)

    block = provider.get_block(-2)
    assert block.number == start_block + 2


def test_get_negative_block_number_out_of_range(provider, contract):
    _ = contract  # We have blocks because the contract was deployed.

    # Also tests against bug where every error was considered a `VirtualMachineError`.
    with pytest.raises(StarknetProviderError, match=r"Block with number '-\d*' not found."):
        provider.get_block(-46346)


def test_get_transactions_by_block(provider, account, contract):
    # Transact to create data.
    expected_value = 123
    contract.increase_balance(account.address, expected_value, sender=account)

    transactions = [t for t in provider.get_transactions_by_block("latest")]

    expected_chain_id = provider.chain_id
    expected_abi = [
        a for a in account.get_contract_type().mutable_methods if a.name == "__execute__"
    ][0]
    expected_nonce = account.nonce - 1
    assert len(transactions) == 1
    assert transactions[0].chain_id == expected_chain_id
    assert transactions[0].method_abi == expected_abi
    assert transactions[0].receiver == account.address
    assert transactions[0].value == 0
    assert is_checksum_address(transactions[0].receiver)
    expected_data = [
        1,
        provider.starknet.encode_address(contract.address),
        get_selector_from_name("increase_balance"),
        0,
        2,
        2,
        provider.starknet.encode_address(account.address),
        expected_value,
        expected_nonce,
    ]
    assert transactions[0].data == expected_data
    assert transactions[0].total_transfer_value == transactions[0].max_fee + transactions[0].value


def test_set_timestamp(provider, account, contract):
    start_time = provider.get_block("pending").timestamp
    provider.set_timestamp(start_time + 8600)
    contract.increase_balance(account.address, 123, sender=account)
    curr_time = time.time()
    assert pytest.approx(curr_time + 8600) == provider.get_block("latest").timestamp


def test_estimate_gas_cost_external_method(contract, account, provider):
    estimated_fee = contract.increase_balance.estimate_gas_cost(account.address, 1, sender=account)
    assert estimated_fee > 100_000_000_000_000

    receipt = contract.increase_balance(account.address, 1, sender=account)
    assert receipt.actual_fee > estimated_fee
    assert receipt.max_fee > estimated_fee
    assert receipt.total_fees_paid == receipt.actual_fee
    assert not receipt.ran_out_of_gas
    assert provider.gas_price >= 100_000_000_000


def test_estimate_gas_cost_view_method(contract, account, provider):
    estimated_fee = contract.get_balance.estimate_gas_cost(account.address, sender=account)
    assert estimated_fee > 100_000_000_000_000
    assert provider.gas_price >= 100_000_000_000


@pytest.mark.xfail(reason="https://github.com/ApeWorX/ape/issues/931", strict=True)
def test_estimate_gas_cost_view_method_2(contract, account):
    estimated_fee = contract.get_balance.estimate_gas_cost(account, sender=account)
    assert estimated_fee > 100_000_000_000_000
