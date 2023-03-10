# Contracts

You can learn more about interacting with contracts from the ApeWorX documentation about [contracts](https://docs.apeworx.io/ape/stable/userguides/contracts.html#contracts).

## Declare and Deploy Contracts

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

### Factory Contracts

Alternatively, you can use the class hash in a `deploy()` system call in a local factory contract.
Let's say for example I have the following Cairo factory contract:

```
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

## Contract Interaction

You can learn more about contract inteacting from the ApeWorX documentation about [contracts](https://docs.apeworx.io/ape/stable/userguides/contracts.html).

**NOTE**: Currently, to pass in arrays as arguments, you have to also include the array size beforehand:

```python
receipt = contract.store_my_list(3, [1, 2, 3])
```
