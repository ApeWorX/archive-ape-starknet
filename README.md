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

You can access accounts using 

```
ape starknet accounts
```

Learn more about accounts by following the [accounts guide](https://docs.apeworx.io/ape-starknet/stable/userguides/accounts.html).

### Testing

Out of the box, `ape-starknet` comes with development accounts.
Access them like this:

```python
from ape import accounts

container = accounts.containers["starknet"]
owner = container.test_accounts[0]
```

See the guide about [Testing](https://docs.apeworx.io/ape-starknet/stable/userguides/testing.html) to learn more about test accounts and testing with the starknet plugin.

### Contracts

In Starknet, you can declare contract types by publishing them to the chain.
This allows other contracts to create instances of them using the [deploy system call](https://www.cairo-lang.org/docs/hello_starknet/deploying_from_contracts.html).

Learn more about contracts by following the [contracts guide](https://docs.apeworx.io/ape/stable/userguides/contracts.html).

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
