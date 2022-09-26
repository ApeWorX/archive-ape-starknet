%lang starknet

from starkware.cairo.common.uint256 import Uint256


@contract_interface
namespace IFireEvents {
    func fire_events(recipient: felt, amount0: Uint256, amount1: Uint256) -> () {
    }
}
