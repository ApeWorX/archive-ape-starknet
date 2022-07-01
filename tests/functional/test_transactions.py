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
