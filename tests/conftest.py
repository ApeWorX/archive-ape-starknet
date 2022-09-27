import json
import shutil
from pathlib import Path
from tempfile import mkdtemp
from typing import cast

import ape
import pytest
from ape.api.networks import LOCAL_NETWORK_NAME, EcosystemAPI
from ethpm_types import ContractType

from ape_starknet import tokens as _tokens
from ape_starknet.accounts import StarknetAccountContracts, StarknetKeyfileAccount
from ape_starknet.utils import PLUGIN_NAME

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
PUBLIC_KEY = "0x140dfbab0d711a23dd58842be2ee16318e3de1c7"
CONTRACT_ADDRESS = "0x6b7243AA4edbe5BD629c6712B3aC9639B160480A7730A31483F7B387463a183"

# Purposely pick a number larest enough to test Uint256 logic
TOKEN_INITIAL_SUPPLY = 2 * 2**128

ETH_CONTRACT_TYPE = ContractType.parse_obj(
    {
        "abi": [
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": False, "name": "prevNum", "type": "uint256"},
                    {"indexed": True, "name": "newNum", "type": "uint256"},
                ],
                "name": "NumberChange",
                "type": "event",
            },
            {"inputs": [], "stateMutability": "nonpayable", "type": "constructor"},
            {
                "inputs": [{"name": "num", "type": "uint256"}],
                "name": "setNumber",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            },
            {
                "inputs": [],
                "name": "owner",
                "outputs": [{"name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function",
            },
            {
                "inputs": [],
                "name": "myNumber",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function",
            },
            {
                "inputs": [],
                "name": "prevNumber",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function",
            },
        ],
        "contractName": "EthContract",
        "deploymentBytecode": {
            "bytecode": "0x3360005561012261001c6300000000396101226000016300000000f3600436101561000d57610117565b60003560e01c3461011d57633fb5c1cb81186100d057600054331461008957600b6040527f21617574686f72697a65640000000000000000000000000000000000000000006060526040506040518060600181600003601f1636823750506308c379a06000526020602052601f19601f6040510116604401601cfd5b60056004351461011d576001546002556004356001556004357f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f135760025460405260206040a2005b638da5cb5b81186100e75760005460405260206040f35b6323fd0e4081186100fe5760015460405260206040f35b634825cf6f81186101155760025460405260206040f35b505b60006000fd5b600080fd"  # noqa: E501
        },
        "devdoc": {},
        "runtimeBytecode": {
            "bytecode": "0x600436101561000d57610117565b60003560e01c3461011d57633fb5c1cb81186100d057600054331461008957600b6040527f21617574686f72697a65640000000000000000000000000000000000000000006060526040506040518060600181600003601f1636823750506308c379a06000526020602052601f19601f6040510116604401601cfd5b60056004351461011d576001546002556004356001556004357f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f135760025460405260206040a2005b638da5cb5b81186100e75760005460405260206040f35b6323fd0e4081186100fe5760015460405260206040f35b634825cf6f81186101155760025460405260206040f35b505b60006000fd5b600080fd"  # noqa: E501
        },
        "sourceId": "EthContract.vy",
        "userdoc": {},
    }
)


@pytest.fixture(scope="session")
def existing_key_file_alias():
    return EXISTING_KEY_FILE_ALIAS


@pytest.fixture(scope="session")
def contract_address():
    return CONTRACT_ADDRESS


@pytest.fixture(scope="session")
def password():
    return PASSWORD


@pytest.fixture(scope="session")
def public_key():
    return PUBLIC_KEY


@pytest.fixture(scope="session")
def token_initial_supply():
    return TOKEN_INITIAL_SUPPLY


@pytest.fixture(scope="session")
def project_path():
    return projects_directory / "project"


@pytest.fixture(scope="session")
def token_project_path():
    return projects_directory / "token"


@pytest.fixture(scope="session")
def proxy_project_path():
    return projects_directory / "proxy"


@pytest.fixture(scope="session")
def data_folder():
    return Path(__file__).parent / "data"


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
def convert():
    return ape.convert


@pytest.fixture(scope="session")
def chain():
    return ape.chain


@pytest.fixture(scope="session")
def provider(chain):
    return chain.provider


@pytest.fixture(scope="session")
def tokens():
    return _tokens


@pytest.fixture(scope="session")
def explorer(provider):
    return provider.starknet_explorer


@pytest.fixture(scope="session")
def eth_contract_type():
    return ETH_CONTRACT_TYPE


@pytest.fixture(autouse=True, scope="session")
def clean_projects():
    def clean():
        for project in projects_directory.iterdir():
            if not project.is_dir() or project.name.startswith("."):
                continue

            cache_dir = project / ".build"
            if not cache_dir.is_dir():
                continue

            shutil.rmtree(cache_dir)

    clean()
    yield
    clean()


@pytest.fixture(scope="session", autouse=True)
def connection():
    network = f"{PLUGIN_NAME}:{LOCAL_NETWORK_NAME}:{PLUGIN_NAME}"
    with ape.networks.parse_network_choice(network) as provider:
        yield provider


# Ensures only ever deploy contracts once.
@pytest.fixture(autouse=True, scope="session")
def deploy_contracts(
    clean_projects,
    config,
    project_path,
    token_project_path,
    proxy_project_path,
    account,
    token_initial_supply,
):
    _ = clean_projects  # Ensure no .build folders

    with config.using_project(project_path) as project:
        contract = project.MyContract.deploy()
        contract.initialize(sender=account)

    with config.using_project(token_project_path) as project:
        token_contract = project.TestToken.deploy(
            123123, 321321, token_initial_supply, account.address
        )
        project.UseToken.deploy()
        _tokens.add_token("test_token", LOCAL_NETWORK_NAME, token_contract.address)

    with config.using_project(proxy_project_path) as project:
        proxy_contract = project.Proxy.deploy(token_contract.address)
        _tokens.add_token("proxy_token", LOCAL_NETWORK_NAME, proxy_contract.address)


@pytest.fixture
def project(config, project_path):
    with config.using_project(project_path) as project:
        yield project


@pytest.fixture
def token_project(config, token_project_path):
    with config.using_project(token_project_path) as project:
        yield project


@pytest.fixture
def proxy_project(config, proxy_project_path):
    with config.using_project(proxy_project_path) as project:
        yield project


@pytest.fixture
def contract(project):
    return project.MyContract.deployments[-1]


@pytest.fixture
def factory_contract_container(project):
    return project.ContractFactory


@pytest.fixture
def token_contract(token_project):
    return token_project.TestToken.deployments[-1]


@pytest.fixture
def token_user_contract(token_project):
    return token_project.UseToken.deployments[-1]


@pytest.fixture
def proxy_token_contract(proxy_project):
    return proxy_project.Proxy.deployments[-1]


@pytest.fixture
def initial_balance(contract, account):
    return contract.get_balance(account.address)


@pytest.fixture(scope="session")
def account_container(accounts):
    return cast(StarknetAccountContracts, accounts.containers[PLUGIN_NAME])


@pytest.fixture(scope="session")
def account(account_container, provider):
    _ = provider  # Connection required
    return account_container.test_accounts[0]


@pytest.fixture(scope="session")
def second_account(account_container, provider):
    _ = provider  # Connection required
    return account_container.test_accounts[1]


@pytest.fixture(scope="session")
def eth_account(accounts):
    return accounts.test_accounts[0]


@pytest.fixture(scope="session")
def ephemeral_account(account_container, provider):
    _ = provider  # Need connection to deploy account.
    account_container.deploy_account(ALIAS)
    return account_container.load(ALIAS)


@pytest.fixture(scope="session")
def ecosystem(provider) -> EcosystemAPI:
    return provider.network.ecosystem


@pytest.fixture(scope="session")
def key_file_account_data():
    return {
        "address": PUBLIC_KEY.replace("0x", ""),
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


@pytest.fixture(scope="session")
def argent_x_key_file_account_data():
    return {
        "address": PUBLIC_KEY.replace("0x", ""),
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


@pytest.fixture(scope="session")
def ephemeral_account_data():
    return {
        "private_key": 509219664670742235607272813021130138373595301613956902800973975925797957544,
        "public_key": 2068822281043178075870469557539081791152169138879468456959920393634230618024,
    }


@pytest.fixture
def key_file_account(config, key_file_account_data):
    temp_accounts_dir = Path(config.DATA_FOLDER) / "starknet"
    temp_accounts_dir.mkdir(exist_ok=True, parents=True)
    test_key_file_path = temp_accounts_dir / f"{EXISTING_KEY_FILE_ALIAS}.json"

    if test_key_file_path.exists():
        test_key_file_path.unlink()

    test_key_file_path.write_text(json.dumps(key_file_account_data))

    yield StarknetKeyfileAccount(key_file_path=test_key_file_path)

    if test_key_file_path.exists():
        test_key_file_path.unlink()


@pytest.fixture(scope="session")
def traces_testnet_243810(data_folder):
    content = (data_folder / "traces-testnet-block-243810.json").read_text()
    return json.loads(content)["traces"]


@pytest.fixture(scope="session")
def traces_testnet_243810_results(data_folder):
    content = (data_folder / "traces-testnet-block-243810_results.json").read_text()
    return json.loads(content)
