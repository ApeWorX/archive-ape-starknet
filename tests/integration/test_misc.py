from .conftest import ApeStarknetCliRunner


def test_plugin_loads(ape_cli):
    runner = ApeStarknetCliRunner(ape_cli, ["starknet"])
    output = runner.invoke("--help")
    assert "ERROR" not in runner.invoke("--help"), output
