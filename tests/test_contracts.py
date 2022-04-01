def test_deploy(project, provider):
    contract_names = [c for c in project.contracts]
    assert len(contract_names) >= 1, "This test requires the project to have contracts."

    for name in contract_names:
        contract = project.get_contract(name)
        assert contract

        deployment = contract.deploy()
        assert deployment
