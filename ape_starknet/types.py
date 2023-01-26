from functools import reduce
from typing import Any, List, Optional

from ape.api import TransactionAPI
from pydantic import BaseModel
from starkware.crypto.signature.signature import pedersen_hash

from ape_starknet.utils import to_int


def _prepare_message(message: Any) -> List[int]:
    if not isinstance(message, (list, tuple)):
        message = [message]

    converted: List[int] = []
    for value in message:
        if isinstance(value, StarknetSignableMessage):
            converted.extend(_prepare_message(value.message))
        elif isinstance(value, (list, tuple)):
            converted.extend(_prepare_message(value))
        elif isinstance(value, TransactionAPI):
            converted.append(to_int(value.txn_hash))
        else:
            converted.append(to_int(value))

    return converted


class StarknetSignableMessage(BaseModel):
    message: Optional[Any]

    @property
    def message_ints(self) -> List[int]:
        return _prepare_message(self.message)

    @property
    def hash(self) -> int:
        return reduce(lambda x, y: pedersen_hash(y, x), self.message_ints, 0)

    def __str__(self) -> str:
        return str(self.message)

    def __repr__(self) -> str:
        return f"<message={self.message}>"
