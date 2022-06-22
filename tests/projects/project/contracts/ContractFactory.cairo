%lang starknet

from starkware.cairo.common.alloc import alloc
from starkware.starknet.common.syscalls import deploy
from starkware.cairo.common.cairo_builtins import HashBuiltin

@storage_var
func class_hash() -> (class_hash : felt):
end

@event
func contract_deployed(contract_address : felt):
end

@constructor
func constructor{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr,
}(cls_hash : felt):
    class_hash.write(value=cls_hash)
    return ()
end

@external
func create_my_contract{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr,
}():
    let (cls_hash) = class_hash.read()
    let (ptr) = alloc()
    let (contract_addr) = deploy(cls_hash, 123, 0, ptr)
    contract_deployed.emit(contract_address=contract_addr)
    return ()
end
