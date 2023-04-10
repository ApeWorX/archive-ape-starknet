#[contract]
mod Storage {
    #[view]
    fn supports_interface(interface_id: felt252) -> bool {
        true
    }

    #[external]
    fn register_interface(interface_id: felt252) {
    }

    #[event]
    fn event_interface(interface_id: felt252){
    }
}