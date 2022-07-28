%lang starknet

from starkware.cairo.common.alloc import alloc
from starkware.starknet.common.syscalls import deploy
from starkware.cairo.common.cairo_builtins import HashBuiltin
from starkware.cairo.common.bool import FALSE

@storage_var
func class_hash() -> (class_hash : felt):
end

@storage_var
func salt() -> (value : felt):
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
    let (current_salt) = salt.read()
    let (ctor_calldata) = alloc()
    let (contract_addr) = deploy(
        class_hash=cls_hash,
        contract_address_salt=current_salt,
        constructor_calldata_size=0,
        constructor_calldata=ctor_calldata,
        deploy_from_zero=FALSE,
    )
    salt.write(value=current_salt + 1)
    contract_deployed.emit(contract_address=contract_addr)
    return ()
end
