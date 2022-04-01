from pathlib import Path

import pytest

ALIAS = "__TEST_ALIAS__"


@pytest.fixture(autouse=True)
def temp_keyfile_path(config):
    temp_accounts_dir = Path(config.DATA_FOLDER) / "starknet"
    temp_accounts_dir.mkdir(exist_ok=True, parents=True)
    test_keyfile_path = temp_accounts_dir / f"{ALIAS}.json"

    if test_keyfile_path.exists():
        # Corrupted from a previous test
        test_keyfile_path.unlink()

    yield test_keyfile_path

    # Clean-up
    if test_keyfile_path.exists():
        test_keyfile_path.unlink()


def test_create(runner, ape_cli, temp_keyfile_path):
    result = runner.invoke(
        ape_cli, ["starknet", "accounts", "create", ALIAS], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
