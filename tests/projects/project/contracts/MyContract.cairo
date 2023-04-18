#[contract]
mod MyContract {
    use array::ArrayTrait;

    struct Storage {
        initialized: bool,
        balance: LegacyMap<felt252, felt252>,
        last_sum: felt252
    }

    #[event]
    fn BalanceIncreased(amount: felt252){
    }

    #[external]
    fn initialize() {
        let did_init = initialized::read();
        assert(!did_init, 'Already initialized');
        initialized::write(true);
    }

    #[external]
    fn reset() {
        initialized::write(false);
    }

    #[external]
    fn increase_balance(user: felt252, amount: felt252) -> felt252 {
        let did_init = initialized::read();
        assert(did_init, '!initialized');

        let bal = balance::read(user);
        balance::write(user, bal + amount);
        BalanceIncreased(amount);
        return balance::read(user);
    }

    #[external]
    fn get_balance(user: felt252) -> felt252 {
        return balance::read(user);
    }

    #[external]
    fn store_sum(arr: Array::<felt252>) -> felt252 {
        let sum = array_sum(arr);
        last_sum::write(0);
        return 0;
    }

    #[internal]
    fn array_sum(arr: Array::<felt252>) -> felt252 {
        let len = arr.len();
        if len == 0 {
            return 0;
        }

        return 0;
    }
}
