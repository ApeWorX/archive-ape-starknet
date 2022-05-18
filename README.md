# Ape StarkNet

Plugins for the [StarkNet Ethereum L2 networks](https://starkware.co/starknet/).

## Dependencies

* [python3](https://www.python.org/downloads) version 3.7 or greater, python3-dev

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

Deploy a new account:

```bash
ape starknet accounts create <ALIAS> --network starknet:testnet
```

You can deploy the same account to multiple networks.

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

Import an existing account:

```bash
ape starknet accounts import <ALIAS> --address 0x6b7111AA4111e5B2229c3332B66696888164440A773333143333B383333a183 --network starknet:testnet
```

You can also import an account by key-file, including a key-file you exported from your [Argent-X browser wallet](https://www.argent.xyz/argent-x/):

```bash
ape starknet accounts import <ALIAS> --keyfile path/to/keyfile.json
```

You can also delete accounts:

```bash
ape starknet accounts delete <ALIAS> --network starknet:testnet
```

**NOTE**: You don't have to specify the network if your account is only deployed to a single network.

### Mainnet Alpha Whitelist Deployment Token

Currently, to deploy to Alpha-Mainnet, your contract needs to be whitelisted.
You can provide your WL token in a variety of ways.

Via Python code:

```python
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

### Contracts

First, deploy your contract:

```python
from ape import project

contract = project.MyContract.deploy()
```

The ``deploy`` method returns a contract instance from which you can call methods on:

```python
receipt = contract.my_mutable_method(123)
value = contract.my_view_method()
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

## Development

This project is in development and should be considered a beta.
Things might not be in their final state and breaking changes may occur.
Comments, questions, criticisms and pull requests are welcomed.

## License

This project is licensed under the [Apache 2.0](LICENSE).
