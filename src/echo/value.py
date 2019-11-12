from typing import Union, Text


Wrapped = Union[bool, int, str, None]


class Value:

    def __init__(self, wrapped: Wrapped):
        assert not isinstance(wrapped, Value), wrapped
        self.wrapped = wrapped

    def __repr__(self) -> Text:
        return f'Value({self.wrapped!r})'

    def is_falsy(self) -> bool:
        w = self.wrapped
        if isinstance(w, (bool, int, str, type(None), tuple, list)):
            return not bool(w)
        raise NotImplementedError(w)

    def is_truthy(self) -> bool:
        return not self.is_falsy()
