from ape.exceptions import ApeException, ProviderError
from ape.types import AddressType


class StarknetEcosystemError(ApeException):
    """
    A general Starknet ecosystem error.
    """


class StarknetProviderError(ProviderError):
    """
    An error raised by the Starknet provider.
    """


class ContractTypeNotFoundError(StarknetEcosystemError):
    """
    An error raised when unable to locate a contract type.
    """

    def __init__(self, address: AddressType):
        super().__init__(f"Failed to find contract type for '{address}'")
