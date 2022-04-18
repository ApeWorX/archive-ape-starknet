# Declare this file as a StarkNet contract.
%lang starknet

from starkware.cairo.common.cairo_builtins import (
    HashBuiltin, SignatureBuiltin)
from starkware.cairo.common.hash import hash2
from starkware.cairo.common.signature import (
    verify_ecdsa_signature)
from starkware.cairo.common.bool import TRUE, FALSE

# Define a storage variable.
@storage_var
func balance(user : felt) -> (res : felt):
end

@storage_var
func is_initialized() -> (initialized: felt):
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
        range_check_ptr}(user : felt, amount : felt):
    let (initialized) = is_initialized.read()
    assert initialized = TRUE

    let (res) = balance.read(user=user)
    balance.write(user, res + amount)
    balance_increased.emit(amount)
    return ()
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
