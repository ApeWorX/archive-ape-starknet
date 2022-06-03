import json
import os
from pathlib import Path
from tempfile import mkdtemp
from typing import Iterator, cast

import ape
import pytest
from ape.api import EcosystemAPI
from ape.api.networks import LOCAL_NETWORK_NAME

from ape_starknet._utils import PLUGIN_NAME
from ape_starknet.accounts import (
    StarknetAccountContracts,
    StarknetEphemeralAccount,
    StarknetKeyfileAccount,
)
from ape_starknet.provider import StarknetProvider

# NOTE: Ensure that we don't use local paths for these
ape.config.DATA_FOLDER = Path(mkdtemp()).resolve()
ape.config.PROJECT_FOLDER = Path(mkdtemp()).resolve()

_HERE = Path(__file__).parent
projects_directory = Path(__file__).parent / "projects"
project_names = [p.stem for p in projects_directory.iterdir() if p.is_dir()]
ALIAS = "__TEST_ALIAS__"
SECOND_ALIAS = "__TEST_ALIAS_2__"
EXISTING_KEY_FILE_ALIAS = f"{ALIAS}existing_key_file"
EXISTING_EPHEMERAL_ALIAS = f"{ALIAS}existing_ephemeral"
PASSWORD = "123"
PUBLIC_KEY = "140dfbab0d711a23dd58842be2ee16318e3de1c7"
CONTRACT_ADDRESS = "0x6b7243AA4edbe5BD629c6712B3aC9639B160480A7730A31483F7B387463a183"
TOKEN_INITIAL_SUPPLY = 10000000000


@pytest.fixture(scope="session")
def config():
    return ape.config


@pytest.fixture(scope="session")
def accounts():
    return ape.accounts


@pytest.fixture(scope="session")
def networks():
    return ape.networks


@pytest.fixture(scope="session")
def project(request, config):
    project_path = _HERE / "projects" / "project"
    os.chdir(project_path)

    with config.using_project(project_path):
        yield ape.project

    os.chdir(_HERE)


@pytest.fixture(scope="module")
def contract_type(project):
    return project.MyContract


@pytest.fixture(scope="module")
def contract(contract_type, provider):
    deployed_contract = contract_type.deploy()
    deployed_contract.initialize()
    return deployed_contract


@pytest.fixture
def initial_balance(contract, account):
    return contract.get_balance(account.address)


@pytest.fixture(scope="session")
def provider() -> Iterator[StarknetProvider]:
    network = f"{PLUGIN_NAME}:{LOCAL_NETWORK_NAME}:{PLUGIN_NAME}"
    with ape.networks.parse_network_choice(network) as provider:
        yield provider


@pytest.fixture(scope="session")
def account_container(accounts):
    return cast(StarknetAccountContracts, accounts.containers[PLUGIN_NAME])


@pytest.fixture(scope="session")
def account(account_container, provider):
    _ = provider  # Need connection to deploy account.
    account_container.deploy_account(ALIAS)
    yield account_container.load(ALIAS)
    account_container.delete_account(ALIAS)


@pytest.fixture(scope="session")
def second_account(account_container, provider):
    _ = provider  # Need connection to deploy account.
    account_container.deploy_account(SECOND_ALIAS)
    yield account_container.load(SECOND_ALIAS)
    account_container.delete_account(SECOND_ALIAS)


@pytest.fixture
def ecosystem(provider) -> EcosystemAPI:
    return provider.network.ecosystem


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


@pytest.fixture
def key_file_account_data():
    return {
        "address": "140dfbab0d711a23dd58842be2ee16318e3de1c7",
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": {"iv": "608494faf88e2d2aea2faac844504233"},
            "ciphertext": "78789f5d4fc5054c18342f020473ecd7c8f75ff2050cdee548121446b40a8ffb",
            "kdf": "scrypt",
            "kdfparams": {
                "dklen": 32,
                "n": 262144,
                "r": 1,
                "p": 8,
                "salt": "c1bbae92537eb53d9ffa3790740bcdb4",
            },
            "mac": "9684c62113753054fc893ffa1b7ae704c65a454f5f89c3b55cc986798d8d5a58",
        },
        "id": "393bb446-55fb-42ec-bd35-ada0b25e17cf",
        "version": 3,
        "ape-starknet": {
            "version": "0.1.0",
            "deployments": [
                {
                    "network_name": "testnet",
                    "contract_address": CONTRACT_ADDRESS,
                },
                {
                    "network_name": "mainnet",
                    "contract_address": CONTRACT_ADDRESS,
                },
            ],
        },
    }


@pytest.fixture
def argent_x_key_file_account_data():
    return {
        "address": "140dfbab0d711a23dd58842be2ee16318e3de1c7",
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": {"iv": "608494faf88e2d2aea2faac844504233"},
            "ciphertext": "78789f5d4fc5054c18342f020473ecd7c8f75ff2050cdee548121446b40a8ffb",
            "kdf": "scrypt",
            "kdfparams": {
                "dklen": 32,
                "n": 262144,
                "r": 1,
                "p": 8,
                "salt": "c1bbae92537eb53d9ffa3790740bcdb4",
            },
            "mac": "9684c62113753054fc893ffa1b7ae704c65a454f5f89c3b55cc986798d8d5a58",
        },
        "id": "393bb446-55fb-42ec-bd35-ada0b25e17cf",
        "version": 3,
        "argent": {
            "version": "0.1.0",
            "accounts": [
                {
                    "network": "goerli-alpha",
                    "address": CONTRACT_ADDRESS,
                },
            ],
        },
    }


@pytest.fixture
def ephemeral_account_data():
    return {
        "private_key": 509219664670742235607272813021130138373595301613956902800973975925797957544,
        "public_key": 2068822281043178075870469557539081791152169138879468456959920393634230618024,
    }


@pytest.fixture(autouse=True)
def existing_key_file_account(config, key_file_account_data):
    temp_accounts_dir = Path(config.DATA_FOLDER) / "starknet"
    temp_accounts_dir.mkdir(exist_ok=True, parents=True)
    test_key_file_path = temp_accounts_dir / f"{EXISTING_KEY_FILE_ALIAS}.json"

    if test_key_file_path.exists():
        test_key_file_path.unlink()

    test_key_file_path.write_text(json.dumps(key_file_account_data))

    yield StarknetKeyfileAccount(key_file_path=test_key_file_path)

    if test_key_file_path.exists():
        test_key_file_path.unlink()


@pytest.fixture(autouse=True)
def existing_ephemeral_account(config, ephemeral_account_data):
    return StarknetEphemeralAccount(
        account_key=EXISTING_EPHEMERAL_ALIAS, raw_account_data=ephemeral_account_data
    )


@pytest.fixture
def token_contract(config, account):
    project_path = _HERE / "projects" / "token"
    os.chdir(project_path)

    with config.using_project(project_path):
        yield ape.project.TestToken.deploy(
            123123, 321321, TOKEN_INITIAL_SUPPLY, account.contract_address
        )
