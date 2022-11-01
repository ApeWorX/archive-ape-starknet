from typing import List

from pydantic import BaseModel, validator


class StarknetSignableMessage(BaseModel):
    value: List[int]

    @validator("value", pre=True, allow_reuse=True)
    def validate_value(cls, value):
        if not isinstance(value, (list, tuple)):
            return [value]
        elif isinstance(value, StarknetSignableMessage):
            return value.value

        return value
