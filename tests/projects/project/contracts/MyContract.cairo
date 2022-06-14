# Declare this file as a StarkNet contract.
%lang starknet

from starkware.cairo.common.alloc import alloc
from starkware.cairo.common.cairo_builtins import (
    HashBuiltin, SignatureBuiltin)
from starkware.cairo.common.hash import hash2
from starkware.cairo.common.signature import (
    verify_ecdsa_signature)
from starkware.cairo.common.bool import TRUE, FALSE

@storage_var
func balance(user : felt) -> (res : felt):
end

@storage_var
func last_sum() -> (sum: felt):
end

@storage_var
func is_initialized() -> (initialized: felt):
end

@storage_var
func array_get_counter() -> (res: felt):
end

@event
func balance_increased(amount : felt):
end

@external
func initialize{
        syscall_ptr: felt*,
        pedersen_ptr: HashBuiltin*,
        range_check_ptr
    }():
    let (initialized) = is_initialized.read()
    with_attr error_message("Already initialized"):
        assert initialized = FALSE
    end

    is_initialized.write(TRUE)
    return ()
end

@external
func reset{
        syscall_ptr: felt*,
        pedersen_ptr: HashBuiltin*,
        range_check_ptr
    }():
    is_initialized.write(FALSE)
    return ()
end

# Increases the balance by the given amount.
@external
func increase_balance{
        syscall_ptr : felt*, pedersen_ptr : HashBuiltin*,
        range_check_ptr}(user : felt, amount : felt) -> (balance):
    let (initialized) = is_initialized.read()
    assert initialized = TRUE

    let (current_balance) = balance.read(user=user)
    balance.write(user, current_balance + amount)
    balance_increased.emit(amount)
    let (new_balance) = balance.read(user=user)
    return (new_balance)
end

@external
func store_sum{
        syscall_ptr : felt*, pedersen_ptr : HashBuiltin*,
        range_check_ptr}(arr_len: felt, arr : felt*) -> (sum):
    let (calc) = array_sum(arr_len, arr)
    last_sum.write(calc)
    return (calc)
end

@external
func get_array{
        syscall_ptr : felt*, pedersen_ptr : HashBuiltin*,
        range_check_ptr}() -> (arr_len: felt, arr: felt*):
    const ARRAY_SIZE = 3
    let (ptr) = alloc()
    assert [ptr] = 1
    assert [ptr + 1] = 2
    assert [ptr + 2] = 3
    let (current_count) = array_get_counter.read()
    array_get_counter.write(current_count + 1)
    return (ARRAY_SIZE, ptr)
end

@view
func view_array{
        syscall_ptr : felt*, pedersen_ptr : HashBuiltin*,
        range_check_ptr}() -> (arr_len: felt, arr: felt*):
    const ARRAY_SIZE = 3
    let (ptr) = alloc()
    assert [ptr] = 1
    assert [ptr + 1] = 2
    assert [ptr + 2] = 3
    return (ARRAY_SIZE, ptr)
end

func array_sum(arr_len: felt, arr : felt*) -> (sum):
    if arr_len == 0:
        return (sum=0)
    end

    # size is not zero.
    let (sum_of_rest) = array_sum(arr_len=arr_len - 1, arr=arr + 1)
    return (sum=[arr] + sum_of_rest)
end

@view
func get_last_sum{
        syscall_ptr : felt*, pedersen_ptr : HashBuiltin*,
        range_check_ptr}() -> (res : felt):
    let (res) = last_sum.read()
    return (res)
end

# Increases the balance of the given user by the given amount.
@external
func increase_balance_signed{
        syscall_ptr : felt*, pedersen_ptr : HashBuiltin*,
        range_check_ptr, ecdsa_ptr : SignatureBuiltin*}(
        user : felt, amount : felt, sig : (felt, felt)):
    # Compute the hash of the message.
    # The hash of (x, 0) is equivalent to the hash of (x).
    let (amount_hash) = hash2{hash_ptr=pedersen_ptr}(amount, 0)

    # Verify the user's signature.
    verify_ecdsa_signature(
        message=amount_hash,
        public_key=user,
        signature_r=sig[0],
        signature_s=sig[1])

    let (res) = balance.read(user=user)
    balance.write(user, res + amount)
    return ()
end

# Returns the current balance.
@view
func get_balance{
        syscall_ptr : felt*, pedersen_ptr : HashBuiltin*,
        range_check_ptr}(user : felt) -> (res : felt):
    let (res) = balance.read(user=user)
    return (res)
end
