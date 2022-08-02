%lang starknet

from starkware.cairo.common.alloc import alloc
from starkware.cairo.common.cairo_builtins import HashBuiltin, SignatureBuiltin
from starkware.cairo.common.hash import hash2
from starkware.cairo.common.signature import verify_ecdsa_signature
from starkware.cairo.common.bool import TRUE, FALSE
from starkware.cairo.common.uint256 import Uint256
from starkware.starknet.common.syscalls import get_caller_address

struct ComplexStruct:
    member timestamp : felt
    member value0 : Uint256
    member value1 : Uint256
end

@storage_var
func balance(user : felt) -> (res : felt):
end

@storage_var
func last_sum() -> (sum : felt):
end

@storage_var
func is_initialized() -> (initialized : felt):
end

@storage_var
func array_get_counter() -> (res : felt):
end

@event
func balance_increased(amount : felt):
end

@storage_var
func complex_structs(index : felt) -> (res : ComplexStruct):
end

@external
func initialize{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}():
    let (initialized) = is_initialized.read()
    with_attr error_message("Already initialized"):
        assert initialized = FALSE
    end

    is_initialized.write(TRUE)
    return ()
end

@external
func reset{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}():
    is_initialized.write(FALSE)
    return ()
end

# Increases the balance by the given amount.
@external
func increase_balance{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}(
    user : felt, amount : felt
) -> (balance):
    let (initialized) = is_initialized.read()
    assert initialized = TRUE

    let (current_balance) = balance.read(user=user)
    balance.write(user, current_balance + amount)
    balance_increased.emit(amount)
    let (new_balance) = balance.read(user=user)
    return (new_balance)
end

# Increases the balance of the given user by the given amount.
@external
func increase_balance_signed{
    syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr, ecdsa_ptr : SignatureBuiltin*
}(public_key : felt, user : felt, amount : felt, sig : (felt, felt)):
    # Compute the hash of the message.
    # The hash of (x, 0) is equivalent to the hash of (x).
    let (amount_hash) = hash2{hash_ptr=pedersen_ptr}(amount, 0)

    # Verify the user's signature.
    verify_ecdsa_signature(
        message=amount_hash, public_key=public_key, signature_r=sig[0], signature_s=sig[1]
    )

    let (res) = balance.read(user=user)
    balance.write(user, res + amount)
    return ()
end

# Returns the current balance.
@view
func get_balance{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}(
    user : felt
) -> (res : felt):
    let (res) = balance.read(user=user)
    return (res)
end

@external
func store_sum{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}(
    arr_len : felt, arr : felt*
) -> (sum):
    let (calc) = array_sum(arr_len, arr)
    last_sum.write(calc)
    return (calc)
end

@external
func get_caller{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (caller):
    let (caller) = get_caller_address()
    return (caller)
end

func array_sum(arr_len : felt, arr : felt*) -> (sum):
    if arr_len == 0:
        return (sum=0)
    end

    # size is not zero.
    let (sum_of_rest) = array_sum(arr_len=arr_len - 1, arr=arr + 1)
    return (sum=[arr] + sum_of_rest)
end

@view
func get_last_sum{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    res : felt
):
    let (res) = last_sum.read()
    return (res)
end

@external
func store_complex_struct{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}(
    complex_struct : ComplexStruct
) -> (res : ComplexStruct):
    complex_structs.write(0, complex_struct)
    let (stored_complex_struct : ComplexStruct) = complex_structs.read(0)
    return (res=stored_complex_struct)
end

#
# Methods for returndata, and return_value, tests.
# Should always define 2 methods:
#   - the external one: my_method_external()
#   - the view one: my_method_view()
#
# Note: keep them alphabetically sorted.
#

@external
func array_external{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    arr_len : felt, arr : felt*
):
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
func array_view{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    arr_len : felt, arr : felt*
):
    const ARRAY_SIZE = 3
    let (ptr) = alloc()
    assert [ptr] = 1
    assert [ptr + 1] = 2
    assert [ptr + 2] = 3
    let (current_count) = array_get_counter.read()
    array_get_counter.write(current_count + 1)
    return (ARRAY_SIZE, ptr)
end

@external
func array_complex_struct_external{
    syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr
}() -> (complex_structs_len : felt, complex_structs : ComplexStruct*):
    let value0 = Uint256(123, 0)
    let value1 = Uint256(0, 123)
    let zero = Uint256(0, 0)
    let my_struct0 = ComplexStruct(0, value0, value1)
    let my_struct1 = ComplexStruct(1, value1, value0)
    let my_struct2 = ComplexStruct(2, zero, zero)

    alloc_locals
    let (local complex_structs : ComplexStruct*) = alloc()
    assert complex_structs[0] = my_struct0
    assert complex_structs[1] = my_struct1
    assert complex_structs[2] = my_struct2
    return (complex_structs_len=3, complex_structs=complex_structs)
end

@view
func array_complex_struct_view{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}(
    ) -> (complex_structs_len : felt, complex_structs : ComplexStruct*):
    let value0 = Uint256(123, 0)
    let value1 = Uint256(0, 123)
    let zero = Uint256(0, 0)
    let my_struct0 = ComplexStruct(0, value0, value1)
    let my_struct1 = ComplexStruct(1, value1, value0)
    let my_struct2 = ComplexStruct(2, zero, zero)

    alloc_locals
    let (local complex_structs : ComplexStruct*) = alloc()
    assert complex_structs[0] = my_struct0
    assert complex_structs[1] = my_struct1
    assert complex_structs[2] = my_struct2
    return (complex_structs_len=3, complex_structs=complex_structs)
end

@external
func array_uint256_external{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}(
    ) -> (amounts_len : felt, amounts : Uint256*):
    alloc_locals
    let (local amounts : Uint256*) = alloc()
    assert amounts[0] = Uint256(123, 0)
    assert amounts[1] = Uint256(0, 123)
    assert amounts[2] = Uint256(0, 0)
    return (amounts_len=3, amounts=amounts)
end

@view
func array_uint256_view{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    amounts_len : felt, amounts : Uint256*
):
    alloc_locals
    let (local amounts : Uint256*) = alloc()
    assert amounts[0] = Uint256(123, 0)
    assert amounts[1] = Uint256(0, 123)
    assert amounts[2] = Uint256(0, 0)
    return (amounts_len=3, amounts=amounts)
end

@external
func complex_struct_external() -> (res : ComplexStruct):
    let value0 = Uint256(123, 0)
    let value1 = Uint256(0, 123)
    let res = ComplexStruct(1234, value0, value1)
    return (res=res)
end

@view
func complex_struct_view() -> (res : ComplexStruct):
    let value0 = Uint256(123, 0)
    let value1 = Uint256(0, 123)
    let res = ComplexStruct(1234, value0, value1)
    return (res=res)
end

@external
func felt_external{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    res : felt
):
    return (res=2)
end

@view
func felt_view{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (res : felt):
    return (res=2)
end

@external
func mix_external{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    start : felt,
    arr_len : felt,
    arr : felt*,
    some_uint256 : Uint256,
    arr2_len : felt,
    arr2 : felt*,
    suffix : felt,
    last_uint256 : Uint256,
):
    alloc_locals

    let (local arr : felt*) = alloc()
    assert arr[0] = 3
    assert arr[1] = 4

    let some_uint256 = Uint256(123, 0)

    let (local arr2 : felt*) = alloc()
    assert arr2[0] = 8
    assert arr2[1] = 9
    assert arr2[2] = 10

    let last_uint256 = Uint256(0, 123)

    return (
        start=1,
        arr_len=2,
        arr=arr,
        some_uint256=some_uint256,
        arr2_len=3,
        arr2=arr2,
        suffix=11,
        last_uint256=last_uint256,
    )
end

@view
func mix_view{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    start : felt,
    arr_len : felt,
    arr : felt*,
    some_uint256 : Uint256,
    arr2_len : felt,
    arr2 : felt*,
    suffix : felt,
    last_uint256 : Uint256,
):
    alloc_locals

    let (local arr : felt*) = alloc()
    assert arr[0] = 3
    assert arr[1] = 4

    let some_uint256 = Uint256(123, 0)

    let (local arr2 : felt*) = alloc()
    assert arr2[0] = 8
    assert arr2[1] = 9
    assert arr2[2] = 10

    let last_uint256 = Uint256(0, 123)

    return (
        start=1,
        arr_len=2,
        arr=arr,
        some_uint256=some_uint256,
        arr2_len=3,
        arr2=arr2,
        suffix=11,
        last_uint256=last_uint256,
    )
end

@external
func uint256_external{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    res : Uint256
):
    let res = Uint256(1, 0)
    return (res=res)
end

@view
func uint256_view{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    res : Uint256
):
    let res = Uint256(1, 0)
    return (res=res)
end

@external
func uint256s_external{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    res1 : Uint256, res2 : Uint256, res3 : Uint256
):
    let res1 = Uint256(123, 0)
    let res2 = Uint256(0, 123)
    let res3 = Uint256(0, 0)
    return (res1=res1, res2=res2, res3=res3)
end

@view
func uint256s_view{syscall_ptr : felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (
    res1 : Uint256, res2 : Uint256, res3 : Uint256
):
    let res1 = Uint256(123, 0)
    let res2 = Uint256(0, 123)
    let res3 = Uint256(0, 0)
    return (res1=res1, res2=res2, res3=res3)
end
