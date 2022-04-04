import json
from pathlib import Path

import pytest

ALIAS = "__TEST_ALIAS__"
PASSWORD = "a"


@pytest.fixture(autouse=True)
def existing_key_file_account(config):
    temp_accounts_dir = Path(config.DATA_FOLDER) / "starknet"
    temp_accounts_dir.mkdir(exist_ok=True, parents=True)
    test_key_file_path = temp_accounts_dir / f"{ALIAS}_2.json"

    if test_key_file_path.exists():
        test_key_file_path.unlink()

    contract_address = "0x122345f379DfB10cE77AF7787677177254977Ec6b774b3677D7779dF99d99"
    key_file_data = {
        "public_key": "7e5f4552091a69125d5dfcb7b8c2659029395bdf",
        "deployments": [
            {
                "contract_address": contract_address,
                "network_name": "testnet",
            }
        ],
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": {"iv": "7bc492fb5dca4fe80fd47645b2aad0ff"},
            "ciphertext": "43beb65018a35c31494f642ec535315897634b021d7ec5bb8e0e2172387e2812",
            "kdf": "scrypt",
            "kdfparams": {
                "dklen": 32,
                "n": 262144,
                "r": 1,
                "p": 8,
                "salt": "4b127cb5ddbc0b3bd0cc0d2ef9a89bec",
            },
            "mac": "6a1d520975a031e11fc16cff610f5ae7476bcae4f2f598bc59ccffeae33b1caa",
        },
        "id": "ee424db9-da20-405d-bd75-e609d3e2b4ad",
        "version": 3,
    }

    test_key_file_path.write_text(json.dumps(key_file_data))

    yield

    if test_key_file_path.exists():
        test_key_file_path.unlink()


def test_accounts(runner, ape_cli, existing_key_file_account):
    """
    Integration test for accounts.
    It all happens under one test because it is really slow to deploy accounts.
    """

    result = runner.invoke(
        ape_cli, ["starknet", "accounts", "create", ALIAS], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output

    # Make sure account shows up in `list` command.
    result = runner.invoke(ape_cli, ["starknet", "accounts", "list"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert ALIAS in result.output

    # Verify existing key-file accounts are also included
    assert f"{ALIAS}_2" in result.output

    result = runner.invoke(
        ape_cli, ["starknet", "accounts", "delete", ALIAS], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert ALIAS in result.output

    result = runner.invoke(
        ape_cli,
        ["starknet", "accounts", "delete", f"{ALIAS}_2"],
        catch_exceptions=False,
        input=PASSWORD,
    )
    assert result.exit_code == 0, result.output
    assert f"{ALIAS}_2" in result.output

    # Make sure account no-longer shows up in `list` command.
    result = runner.invoke(ape_cli, ["starknet", "accounts", "list"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert ALIAS not in result.output
