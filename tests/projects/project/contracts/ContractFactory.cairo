#[contract]
mod ContractFactory {
    use array::ArrayTrait;
    use starknet::class_hash::ClassHash;
    use starknet::ContractAddress;
    use starknet::syscalls::deploy_syscall;

    struct Storage {
        class_hash: ClassHash,
        salt: felt252
    }

    #[event]
    fn ContractDeployed(contract_address: ContractAddress){
    }

    #[constructor]
    fn constructor(cls_hash: ClassHash) {
        class_hash::write(cls_hash);
    }

    #[external]
    fn create_my_contract() -> ContractAddress {
        let cls_hash = class_hash::read();
        let _salt = salt::read();
        let mut ctor_calldata = ArrayTrait::new();
        let result = deploy_syscall(cls_hash, _salt, ctor_calldata.span(), false);
        let (addr, _) = result.unwrap_syscall();
        addr
    }
}
