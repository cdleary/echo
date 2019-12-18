from typing import Union, Text


Wrapped = Union[bool, int, str, None]


class Value:

    def __init__(self, wrapped: Wrapped):
        assert not isinstance(wrapped, Value), wrapped
        self.wrapped = wrapped

    def __repr__(self) -> Text:
        return f'Value({self.wrapped!r})'
