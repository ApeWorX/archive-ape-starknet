from typing import List

import pytest
from ape._cli import cli
from click.testing import CliRunner


@pytest.fixture(scope="session")
def ape_cli():
    yield cli


class ApeStarknetCliRunner:
    runner = CliRunner()

    def __init__(self, cli, base_cmd: List[str]):
        self._cli = cli
        self.base_cmd = base_cmd

    def invoke(self, *cmd, input=None, ensure_successful: bool = True):
        ape_cmd = self._get_cmd(*cmd)
        catch_exceptions = not ensure_successful
        result = self.runner.invoke(
            self._cli, ape_cmd, catch_exceptions=catch_exceptions, input=input
        )

        if ensure_successful:
            assert result.exit_code == 0, result.output

        return result.output

    def _get_cmd(self, *args) -> List[str]:
        return [*self.base_cmd, *args]
