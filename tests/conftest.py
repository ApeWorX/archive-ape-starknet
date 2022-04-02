import os
from pathlib import Path
from typing import Iterator

import ape
import pytest
from ape._cli import cli
from ape.api import EcosystemAPI, ProviderAPI
from click.testing import CliRunner

projects_directory = Path(__file__).parent / "projects"
project_names = [p.stem for p in projects_directory.iterdir() if p.is_dir()]


@pytest.fixture(scope="session")
def config():
    return ape.config


@pytest.fixture(scope="session")
def project(request, config):
    here = Path(__file__).parent
    project_path = here / "projects" / "project"
    os.chdir(project_path)

    with config.using_project(project_path):
        yield ape.project

    os.chdir(here)


@pytest.fixture(scope="session")
def provider() -> Iterator[ProviderAPI]:
    with ape.networks.parse_network_choice("starknet:local:starknet") as provider:
        yield provider


@pytest.fixture
def ecosystem(provider) -> EcosystemAPI:
    return provider.network.ecosystem


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def ape_cli():
    return cli


@pytest.fixture(autouse=True)
def clean_cache(project):
    """
    Use this fixture to ensure a project
    does not have a cached compilation.
    """
    cache_file = project._project.manifest_cachefile
    if cache_file.exists():
        cache_file.unlink()

    yield

    if cache_file.exists():
        cache_file.unlink()
