import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkdtemp
from typing import cast

import ape
import pytest
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractInstance
from ethpm_types import ContractType
from starkware.cairo.lang.compiler.test_utils import short_string_to_felt

from ape_starknet import tokens as _tokens
from ape_starknet.accounts import StarknetAccountContainer, StarknetKeyfileAccount
from ape_starknet.utils import OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH, PLUGIN_NAME

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
PUBLIC_KEY = 367323783092256132793135877206902311054243182689252847590820585364953599456

# Pre-checksummed
CONTRACT_ADDRESS = "0x06b7243aA4eDBe5bD629c6712B3ac9639B160480a7730a31483F7b387463A183"

START_BALANCE = "1000000 ETH"

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


@pytest.fixture
def networks():
    return ape.networks


@pytest.fixture(scope="session")
def convert():
    return ape.convert


@pytest.fixture(scope="session")
def chain():
    return ape.chain


@pytest.fixture(scope="session")
def project(contracts):
    with contracts.use_project() as proj:
        yield proj


@pytest.fixture(scope="session")
def use_local_starknet():
    choice = f"{PLUGIN_NAME}:{LOCAL_NETWORK_NAME}:{PLUGIN_NAME}"
    return ape.networks.parse_network_choice(choice)


@pytest.fixture(scope="session")
def use_local_ethereum():
    return ape.networks.parse_network_choice(f"ethereum:{LOCAL_NETWORK_NAME}")


@pytest.fixture(scope="session", autouse=True)
def connected(use_local_starknet):
    with use_local_starknet:
        yield


@pytest.fixture(scope="session")
def tokens():
    return _tokens


@pytest.fixture
def provider(chain):
    return chain.provider


@pytest.fixture(scope="session")
def explorer(use_local_starknet):
    with use_local_starknet as provider:
        return provider


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


@pytest.fixture(scope="session")
def project_switcher(config, project_path, token_project_path, proxy_project_path):
    projects = {"project": project_path, "token": token_project_path, "proxy": proxy_project_path}

    class ProjectSwitcher:
        @contextmanager
        def use(self, name: str):
            with config.using_project(projects[name]) as project:
                yield project

    return ProjectSwitcher()


@pytest.fixture(scope="session")
def contracts(
    clean_projects,
    project_switcher,
    account,
    token_initial_supply,
    use_local_starknet,
):
    class ContractsDeployer:
        """
        A solution to more lazily deploy session-scoped contracts.
        This is helpful to speed up tests when not using them.
        """

        @property
        def my_contract(self) -> ContractInstance:
            with self.use_project() as project:
                if project.MyContract.deployments:
                    return project.MyContract.deployments[-1]

                # Declare + Deploy contract only once.
                account.declare(project.MyContract)
                contract = project.MyContract.deploy(sender=account)
                contract.initialize(sender=account)
                return contract

        @property
        def token(self):
            with self.use_project(name="token") as project:
                if project.TestToken.deployments:
                    return project.TestToken.deployments[-1]

                account.declare(project.TestToken)
                name = short_string_to_felt("TestToken")
                symbol = short_string_to_felt("TEST")
                contract = project.TestToken.deploy(
                    name, symbol, 18, token_initial_supply, int(account.address, 16), sender=account
                )
                _tokens.add_token("test_token", LOCAL_NETWORK_NAME, contract.address)
                return contract

        @property
        def user_token(self):
            with self.use_project(name="token") as project:
                if project.UseToken.deployments:
                    return project.UseToken.deployments[-1]

                account.declare(project.UseToken)
                return project.UseToken.deploy(sender=account)

        @property
        def proxy(self):
            with self.use_project(name="proxy") as project:
                if project.Proxy.deployments:
                    return project.Proxy.deployments[-1]

                account.declare(project.Proxy)
                contract = project.Proxy.deploy(self.token.address, sender=account)
                _tokens.add_token("proxy_token", LOCAL_NETWORK_NAME, contract.address)
                return contract

        @contextmanager
        def use_project(self, name: str = "project"):
            with use_local_starknet:
                with project_switcher.use(name) as proj:
                    yield proj

    return ContractsDeployer()


@pytest.fixture(scope="session")
def contract(contracts):
    return contracts.my_contract


@pytest.fixture(scope="session")
def token_contract(contracts):
    return contracts.token


@pytest.fixture(scope="session")
def token_user_contract(contracts):
    return contracts.user_token


@pytest.fixture
def initial_balance(contract, account):
    return contract.get_balance(account.address)


@pytest.fixture(scope="session")
def account_container(accounts):
    return cast(StarknetAccountContainer, accounts.containers[PLUGIN_NAME])


@pytest.fixture(scope="session")
def account(account_container, use_local_starknet):
    with use_local_starknet:
        return account_container.test_accounts[0]


@pytest.fixture(scope="session")
def second_account(account_container, use_local_starknet):
    with use_local_starknet:
        return account_container.test_accounts[1]


@pytest.fixture(scope="session")
def eth_account(accounts):
    return accounts.test_accounts[0]


@pytest.fixture(scope="session")
def ephemeral_account(account_container):
    return create_account(account_container)


def create_account(container):
    return container.create_account(ALIAS)


@pytest.fixture(scope="session")
def starknet():
    return ape.networks.starknet


@pytest.fixture(scope="session")
def testnet(starknet):
    return starknet.testnet


@pytest.fixture
def in_starknet_testnet(testnet):
    with testnet.use_provider("starknet"):
        yield


@pytest.fixture(scope="session")
def key_file_account_data():
    return {
        "ape-starknet": {
            "public_key": 367323783092256132793135877206902311054243182689252847590820585364953599456,  # noqa: E501
            "class_hash": 3146761231686369291210245479075933162526514193311043598334639064078158562617,  # noqa: E501
            "salt": 2383401134194309956567840095871463496630094772532838902518655252027359569593,
            "deployments": [
                {"network_name": "testnet", "contract_address": CONTRACT_ADDRESS},
            ],
        },
        "address": "93920847a9ab3c731562461bb7d0fb95a39df9f9",
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": {"iv": "b279075a04c21ed621e466974c64e6e3"},
            "ciphertext": "e3fb18fbd034df62963ac776c04fec9a58a71273cbbd236fa6f22f98a7563e5a",
            "kdf": "scrypt",
            "kdfparams": {
                "dklen": 32,
                "n": 262144,
                "r": 1,
                "p": 8,
                "salt": "810c59cb704d6012ce2002012cbdf735",
            },
            "mac": "f903f6d42efd883e3b402f68c7681857080a889a363e78e7694e143b5a9a9a65",
        },
        "id": "2b50ad6b-d136-4981-b09c-08c006e2ae56",
        "version": 3,
    }


@pytest.fixture(scope="session")
def ephemeral_account_data():
    return {
        "private_key": 509219664670742235607272813021130138373595301613956902800973975925797957544,
        "public_key": 2068822281043178075870469557539081791152169138879468456959920393634230618024,
        "class_hash": OPEN_ZEPPELIN_ACCOUNT_CLASS_HASH,
    }


@pytest.fixture
def key_file_account(config, key_file_account_data):
    temp_accounts_dir = Path(config.DATA_FOLDER) / "starknet"
    temp_accounts_dir.mkdir(exist_ok=True, parents=True)
    test_key_file_path = temp_accounts_dir / f"{EXISTING_KEY_FILE_ALIAS}.json"

    if test_key_file_path.is_file():
        test_key_file_path.unlink()

    test_key_file_path.write_text(json.dumps(key_file_account_data))

    account = StarknetKeyfileAccount(key_file_path=test_key_file_path)
    account.unlock(passphrase="123")

    yield account

    if test_key_file_path.is_file():
        test_key_file_path.unlink()


@pytest.fixture(scope="session")
def traces_testnet_243810(data_folder):
    content = (data_folder / "traces-testnet-block-243810.json").read_text()
    return json.loads(content)["traces"]


@pytest.fixture(scope="session")
def traces_testnet_243810_results(data_folder):
    content = (data_folder / "traces-testnet-block-243810_results.json").read_text()
    return json.loads(content)
