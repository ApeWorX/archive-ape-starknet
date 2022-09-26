%lang starknet

from starkware.cairo.common.cairo_builtins import HashBuiltin
from starkware.cairo.common.uint256 import Uint256
from IFireEvents import IFireEvents


@external
func fireTokenEvent{syscall_ptr: felt*, pedersen_ptr: HashBuiltin*, range_check_ptr}(token: felt) {
    IFireEvents.fire_events(token, 10000000, Uint256(100, 0), Uint256(200, 0));
    return ();
}
