# Quick Start

Plugins for the [StarkNet Ethereum L2 networks](https://starkware.co/starknet/).

## Dependencies

* [python3](https://www.python.org/downloads) version 3.8 or greater, python3-dev

## Installation

### via `pip`

You can install the latest release via [`pip`](https://pypi.org/project/pip/):

```bash
pip install ape-starknet
```

### via `setuptools`

You can clone the repository and use [`setuptools`](https://github.com/pypa/setuptools) for the most up-to-date version:

```bash
git clone https://github.com/ApeWorX/ape-starknet.git
cd ape-starknet
python3 setup.py install
```

## Quick Usage

### Account Management

Accounts are used to execute transactions and sign call data.
Accounts are smart contracts in Starknet.

Out of the box, `ape-starknet` comes with development accounts.
Access them like this:

```python
from ape import accounts

container = accounts.containers["starknet"]
owner = container.test_accounts[0]
```

See the section below about [Testing](#Testing) to learn more about test accounts.

However, when using a live network, you will have to import or create an account first.

To import an account, use the `import` command:

```bash
ape starknet accounts import <ALIAS> --address 0x6b7111AA4111e5B2229c3332B66696888164440A773333143333B383333a183 --network starknet:testnet
```

You can also import an account by key-file, including a key-file you exported from your [Argent-X browser wallet](https://www.argent.xyz/argent-x/):

```bash
ape starknet accounts import <ALIAS> --keyfile path/to/keyfile.json
```

To create a new account, you will use the `create` command:

```bash
ape starknet accounts create <NEW-ALIAS> --network starknet:testnet
```

The `create` command will first generate the public and private key combination and store a local keyfile for the account.
However, it does not deploy the account automatically.
The reason it does not deploy automatically is that the account needs funding to pay for its deployment and there are several ways to achieve this.
See [this section](https://starknet.io/docs/hello_starknet/account_setup.html#transferring-goerli-eth-to-the-account) of the Starknet official guides for more information.

For convenience purposes, if you already have a Starknet account in Ape, you can use that account to fund the creation of new ones.
To do this, use the `--deployment-funder` flag to specify the funder alias of your other account:

```bash
ape starknet accounts create <NEW-ALIAS> --network starknet:testnet --deployment-funder <EXISTING-ALIAS>
```

Otherwise, after you have funded your newly created account an alternative way, you can use the `deploy` command to deploy it:

```bash
ape starknet accounts deploy <NEW-ALIAS>
```

You can create the same account in multiple networks by adjusting the `--network` flag:

```bash
ape starknet accounts create <ALIAS> --network starknet:mainnet
```

See your accounts and all of their deployment addresses:

```bash
ape starknet accounts list
```

shows:

```bash
Alias                      - <ALIAS>
Public key                 - 0x123444444d716666dd88882bE2e99991555DE1c7
Contract address (testnet) - 0x6b7111AA4111e5B2229c3332B66696888164440A773333143333B383333a183
Contract address (mainnet) - 0x7873113A4111e5B2229c3332B66696388163440A373333143333B3833332122
```

You can also delete accounts:

```bash
ape starknet accounts delete <ALIAS> --network starknet:testnet
```

**NOTE**: You don't have to specify the network if your account is only deployed to a single network.

#### Auto-Sign Message

While generally bad practice, sometimes it is necessary to have unlocked keyfile accounts auto-signing messages.
An example would be during testnet automated deployments.
To achieve this, use the ``set_autosign()`` method available on the keyfile accounts:

```python
import keyring
from ape import accounts

# Use keyring package to store secrets
password = keyring.get_password("starknet-testnet-automations", "ci-shared-account")
testnet_account = accounts.load("starknet-testnet-account")
testnet_account.set_autosign(True, passphrase=password)

# Won't prompt for signing or unlocking
testnet_account.sign_message([123])
```

### Declare and Deploy Contracts

In Starknet, you can declare contract types by publishing them to the chain.
This allows other contracts to create instances of them using the [deploy system call](https://www.cairo-lang.org/docs/hello_starknet/deploying_from_contracts.html).

To declare a contract using `ape-starknet`, do the following (in a script or console):

```python
from ape import accounts, project

account = accounts.load("<MY_STARK_ACCOUNT>")
declaration = account.declare(project.MyContract)
print(declaration.class_hash)
```

Then, you can use the `deploy` method to deploy the contracts.
**NOTE**: The `deploy` method in `ape-starknet` makes an invoke-function call against the Starknet public UDC contract.
Learn more about UDC contracts [here](https://community.starknet.io/t/universal-deployer-contract-proposal/1864).

```python
from ape import accounts, project

# This only works if `project.MyContract` was declared previously.
# The class hash is not necessary as an argument. Ape will look it up.
account = accounts.load("<MY_STARK_ACCOUNT>")
account.deploy(project.MyContact)
```

Alternatively, you can use the class hash in a `deploy()` system call in a local factory contract.
Let's say for example I have the following Cairo factory contract:

```cairo
from starkware.cairo.common.alloc import alloc
from starkware.starknet.common.syscalls import deploy
from starkware.cairo.common.cairo_builtins import HashBuiltin

@external
func deploy_my_contract{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr,
}():
    let (current_salt) = salt.read()
    let (class_hash) = ownable_class_hash.read()
    let (calldata_ptr) = alloc()
    let (contract_address) = deploy(
        class_hash=class_hash,
        contract_address_salt=current_salt,
        constructor_calldata_size=0,
        constructor_calldata=calldata_ptr,
    )
    salt.write(value=current_salt + 1)
```

This contract accepts a class hash of a declared contract deploys it.
The following example shows how to use this factory class to deploy other contracts:

```python
from ape import Contract, accounts, networks, project

account = accounts.load("<MY_STARK_ACCOUNT>")
declaration = account.declare(project.MyContract)

# NOTE: Assuming you have a contract named 'ContractFactory'.
factory = project.ContractFactory.deploy(declaration.class_hash)

call_result = factory.deploy_my_contract()
contract_address = networks.starknet.decode_address(call_result)
contract = Contract(contract_address, contract_type=project.MyContract.contract_type)
```

### Contract Interaction

After you have deployed your contracts, you can begin interacting with them.
``deploy`` methods return a contract instance from which you can call methods on:

```python
from ape import project

contract = project.MyContract.deploy()

# Interact with deployed contract
receipt = contract.my_mutable_method(123)
value = contract.my_view_method()
```

You can access the return data from a mutable method's receipt:

```python
receipt = contract.my_mutable_method(123)
result = receipt.return_value
```

Include a sender to delegate the transaction to an account contract:

```python
from ape import accounts

account = accounts.load("my_account")
receipt = contract.my_mutable_method(123, sender=account)
```

**NOTE**: Currently, to pass in arrays as arguments, you have to also include the array size beforehand:

```python
receipt = contract.store_my_list(3, [1, 2, 3])
```

### Testing

#### Accounts

You can use ``starknet-devnet`` accounts in your tests.

```python
import pytest
import ape


@pytest.fixture
def devnet_accounts():
    return ape.accounts.containers["starknet"].test_accounts


@pytest.fixture
def owner(devnet_accounts):
    return devnet_accounts[0]
```

Additionally, any accounts deployed in the local network are **not** saved to disk and are ephemeral.

```python
import pytest
import ape


@pytest.fixture(scope="session")
def ephemeral_account():
    accounts = ape.accounts.containers["starknet"]
    accounts.deploy_account("ALIAS")

    # This account only exists in the devnet and is not a key-file account.
    return accounts.load("ALIAS")
```

### Mainnet Alpha Whitelist Deployment Token

You can deploy contracts by doing:

```python
from ape import project

my_contract = project.MyContract.deploy()
```

### Paying Fees

Starknet fees are currently paid in ETH, which is an ERC-20 on the Starknet chain.
To check your account balance (in ETH), use the `balance` property on the account:

```python
from ape import accounts

acct = accounts.load("Alias")
print(acct.balance)
```

If your account has a positive balance, you can begin paying fees!

To pay fees, you can either manually set the `max_fee` kwarg on an invoke-transaction:

```python
receipt = contract.my_mutable_method(123, max_fee=2900000000000)
```

**NOTE**: By not setting the `max_fee`, it will automatically get set to the value returned from the provider `estimate_gas_cost()` call.
You do **not** need to call `estimate_gas_cost()` explicitly.

### Mainnet Alpha Whitelist Deployment Token

Currently, to deploy to Alpha-Mainnet, your contract needs to be whitelisted.
You can provide your WL token in a variety of ways.

Via Python code:

```python
from ape import project

my_contract = project.MyContract.deploy(token="MY_TOKEN")
```

Via an Environment Variable:

```bash
export ALPHA_MAINNET_WL_DEPLOY_TOKEN="MY_TOKEN"
```

Or, via the `--token` flag when deploying an account:

```bash
ape starknet accounts create MY_ACCOUNT --token MY_TOKEN
```

## Development

This project is in development and should be considered a beta.
Things might not be in their final state and breaking changes may occur.
Comments, questions, criticisms and pull requests are welcomed.
