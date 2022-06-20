from ape.contracts.base import ContractConstructor


def test_deploy_txn_hash(project, convert, provider):
    contract_type = project.MyContract.contract_type
    constructor = ContractConstructor(
        abi=contract_type.constructor, deployment_bytecode=contract_type.get_deployment_bytecode()
    )
    deploy_txn = constructor.serialize_transaction()
    receipt = provider.send_transaction(deploy_txn)

    # Ensure pre-calculated hash equals client response hash.
    assert deploy_txn.txn_hash.hex() == receipt.txn_hash


def test_invoke_txn_hash(contract, provider, account):
    invoke_txn = contract.increase_balance.as_transaction(account.address, 999, sender=account)
    receipt = provider.send_transaction(invoke_txn)

    # Ensure pre-calculated hash equals client response hash.
    assert invoke_txn.txn_hash.hex() == receipt.txn_hash
