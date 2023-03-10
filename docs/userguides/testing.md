# Testing

You can learn more about testing from the ApeWorX documentation on [testing](https://docs.apeworx.io/ape/stable/userguides/testing.html).

## Accounts

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
