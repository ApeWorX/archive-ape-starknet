from ape.exceptions import ApeException, ProviderError


class StarknetEcosystemError(ApeException):
    """
    A general Starknet ecosystem error.
    """


class StarknetProviderError(ProviderError):
    """
    An error raised by the Starknet provider.
    """


class StarknetDevnetSubprocessError(ProviderError):
    """
    An error raised whilst managing the 'starknet-devnet' subprocess.
    """
