// SPDX-License-Identifier: MIT

%lang starknet

from starkware.cairo.common.cairo_builtins import HashBuiltin

// Event for testing that it shows up in downstream contract
@event
func MyEventLib_ParentEvent(favorite_account: felt) {
}

namespace MyEventLib {
    func fire_event{syscall_ptr: felt*, pedersen_ptr: HashBuiltin*, range_check_ptr}(person: felt) -> () {
        MyEventLib_ParentEvent.emit(person);
        return ();
    }
}
