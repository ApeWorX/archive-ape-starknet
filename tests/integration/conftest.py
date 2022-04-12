from typing import List

import pytest
from ape._cli import cli
from click.testing import CliRunner


@pytest.fixture(scope="session")
def ape_cli():
    yield cli


class ApeStarknetCliRunner:
    runner = CliRunner()

    def __init__(self, cli):
        self._cli = cli

    def invoke(self, *cmd, input=None, ensure_successful: bool = True):
        ape_cmd = self._get_cmd(*cmd)
        catch_exceptions = not ensure_successful
        result = self.runner.invoke(
            self._cli, ape_cmd, catch_exceptions=catch_exceptions, input=input
        )

        if ensure_successful:
            assert result.exit_code == 0, result.output

        return result.output

    @staticmethod
    def _get_cmd(*args) -> List[str]:
        return ["starknet", "accounts", *args]


@pytest.fixture
def runner(ape_cli):
    return ApeStarknetCliRunner(ape_cli)
