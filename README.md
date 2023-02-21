# Quick Start

Plugins for the [StarkNet Ethereum L2 networks](https://starkware.co/starknet/).

## Dependencies

- [python3](https://www.python.org/downloads) version 3.8 or greater, python3-dev

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

Learn more about accounts by following the [accounts guide]().

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

You can also deploy contracts by doing:

```python
from ape import accounts, project

account = accounts.load("<MY_STARK_ACCOUNT>")
my_contract = project.MyContract.deploy(sender=account)
```
Learn more about deploying contracts like factory contracts by following the [contracts guide]()

### Contract Interaction

After you have deployed your contracts, you can begin interacting with them.
`deploy` methods return a contract instance from which you can call methods on:

```python
from ape import project

contract = project.MyContract.deploy(sender=account)

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

You can use `starknet-devnet` accounts in your tests.

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

## Development

This project is in development and should be considered a beta.
Things might not be in their final state and breaking changes may occur.
Comments, questions, criticisms and pull requests are welcomed.
