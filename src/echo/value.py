from typing import Union


Wrapped = Union[bool, int, str, None]


class Value:

    def __init__(self, wrapped: Wrapped):
        self.wrapped = wrapped

    def is_falsy(self) -> bool:
        w = self.wrapped
        if isinstance(w, (bool, int, str)):
            return not bool(w)
        raise NotImplementedError

    def is_truthy(self) -> bool:
        return not self.is_falsy()
