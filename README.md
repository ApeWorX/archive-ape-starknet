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

However, when using a live network, you will have to import or create an account first.

#### Importing an Account

To import an account, use the `import` command:

```bash
ape starknet accounts import <ALIAS> \
    --network testnet,testnet2 \
    --address 0x6b7111AA4111e5B2229c3332B66696888164440A773333143333B383333a183 \
    --class-hash "0x025ec026985a3bf9d0cc1fe17326b245dfdc3ff89b8fde106542a3ea56c5a918"
    --salt 123
```

The command above is using a network value of `testnet,testnet2`, meaning both Starknet's Goerli testnet and Goerli testnet2 networks.
You can run the import command more than once to add more networks at a later time.
To add all networks at once, you can also use a `--network` value of `starknet`.

If the account is already added, you can omit the `--address` flag and use the calculated one instead.
If you know the salt the account used to calculate its address, you can provide that with the `--salt` flag.
This will allow future deployments to use the same address.

Importing accounts is complex.
A common use-case is to import your Argent-X wallet.
To do this, you can use the following command:

```bash
ape starknet accounts import <ArgentX-Alias> \
    --network starknet \
    --address 0x6b7111AA4111e5B2229c3332B66696888164440A773333143333B383333a183 \
    --class-hash argentx
```

And then export your Argent-X private key from the app and paste it in the CLI prompt.
Now, you can use your argent-x account to fund and create other accounts!

#### Creating an Account

To create a new account, you can use the `create` command:

```bash
ape starknet accounts create <NEW-ALIAS>
```

By default, new accounts use the Open Zeppelin account contract implementation.
However, if you want to change the class, use the `--class-hash` option:

```bash
CLASS_HASH="0x1a7820094feaf82d53f53f214b81292d717e7bb9a92bb2488092cd306f3993f"
ape starknet accounts create <NEW-ALIAS> --class-hash "${CLASS_HASH}"
```

**NOTE**: You may also need to change the constructor calldata using the `--constructor-calldata` flag when using a different account contract type.

The `create` command will first generate the public and private key combination and store a local keyfile for the account.
However, it does not deploy the account.
The reason it does not deploy is that the account needs funding to pay for its deployment and there are several ways to achieve this.
See [this section](https://starknet.io/docs/hello_starknet/account_setup.html#transferring-goerli-eth-to-the-account) of the Starknet official guides for more information.

#### Deploying an Account

To deploy the new account, use the `deploy` command:

```bash
ape starknet accounts deploy <NEW-ALIAS> --network testnet
```

This only works if the account has been funded.
For convenience purposes, if you have another account with funds, you can use that account to fund the deployment of this one using the `--funder` option:

```bash
ape starknet accounts deploy <NEW-ALIAS> --network testnet --funder <EXISTING-FUNDED-ALIAS>
```

**NOTE**: You cannot use an Ethereum account to send funds to a Starknet account directly.
You must use the [StarkNet L2 bridge](https://goerli.starkgate.starknet.io/) to transfer existing Goerli L1 ETH to and from the L2 account.

#### Listing Accounts

See your accounts and all of their deployment addresses:

```bash
ape starknet accounts list
```

shows:

```bash
Alias                      - <ALIAS>
Public key                 - 0x123444444d716666dd88882bE2e99991555DE1c7
Class hash                 - 0x25ec026985a3bf9d0cc1fe17326b245dfdc3ff89b8fde106542a3ea56c5a918
Contract address (testnet) - 0x6b7111AA4111e5B2229c3332B66696888164440A773333143333B383333a183
Contract address (mainnet) - 0x7873113A4111e5B2229c3332B66696388163440A373333143333B3833332122
```

#### Deleting an Account

You can also delete accounts:

```bash
ape starknet accounts delete <ALIAS> --network testnet,testnet2
```

The `delete` command differs based on its values of `--network` and `--address`:

- To delete all deployments on a given network, use the `--network` option without `--address`.
- To delete all deployments matching an address (regardless of network), use the `--address` option without `--network`.
- To delete a deployment on a network with a particular address, use both `--network` and `--address`.
- Exclude both options to delete the whole account.

Note you can also specify multiple networks, the same as `import`.

#### Auto-Sign Message

While generally bad practice, sometimes it is necessary to have unlocked keyfile accounts auto-signing messages.
An example would be during testnet automated deployments.
To achieve this, use the `set_autosign()` method available on the keyfile accounts:

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

You can also deploy contracts by doing:

```python
from ape import accounts, project

account = accounts.load("<MY_STARK_ACCOUNT>")
my_contract = project.MyContract.deploy(sender=account)
```

Alternatively, you can use the class hash in a `deploy()` system call in a local factory contract.
Let's say for example I have the following Cairo factory contract:

```cairo
from starkware.cairo.common.alloc import alloc
from starkware.starknet.common.syscalls import deploy
from starkware.cairo.common.cairo_builtins import HashBuiltin

@storage_var
func class_hash() -> (class_hash: felt) {
}

@storage_var
func salt() -> (value: felt) {
}

@constructor
func constructor{syscall_ptr: felt*, pedersen_ptr: HashBuiltin*, range_check_ptr}(cls_hash: felt) {
    class_hash.write(value=cls_hash);
    return ();
}

@external
func deploy_my_contract{syscall_ptr: felt*, pedersen_ptr: HashBuiltin*, range_check_ptr}() {
    let (cls_hash) = class_hash.read();
    let (current_salt) = salt.read();
    let (ctor_calldata) = alloc();
    let (contract_addr) = deploy(
        class_hash=cls_hash,
        contract_address_salt=current_salt,
        constructor_calldata_size=0,
        constructor_calldata=ctor_calldata,
        deploy_from_zero=FALSE,
    );
    salt.write(value=current_salt + 1);
    return ();
}
```

This contract accepts a class hash of a declared contract deploys it.
The following example shows how to use this factory class to deploy other contracts:

```python
from ape import Contract, accounts, networks, project

account = accounts.load("<MY_STARK_ACCOUNT>")
declaration = account.declare(project.MyContract)

# NOTE: Assuming you have a contract named 'ContractFactory'.
factory = project.ContractFactory.deploy(declaration.class_hash, sender=account)

call_result = factory.deploy_my_contract()
contract_address = networks.starknet.decode_address(call_result)
contract = Contract(contract_address, contract_type=project.MyContract.contract_type)
```

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
