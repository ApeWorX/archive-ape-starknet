# Accounts

When using a live network, you will have to import or create an account first.

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