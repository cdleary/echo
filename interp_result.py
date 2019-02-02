"""ADT that encapsulates 'interpreter result value or error data'."""

import collections
from enum import Enum
from typing import TypeVar, Union, Generic


T = TypeVar('T')
ExceptionData = collections.namedtuple('ExceptionData',
                                       'traceback parameter exception')


class Result(Generic[T]):

    def __init__(self, value: Union[T, ExceptionData]):
        self.value = value

    def is_exception(self) -> bool:
        return isinstance(self.value, ExceptionData)

    def get_value(self) -> T:
        assert not isinstance(self.value, ExceptionData)
        return self.value

    def get_exception(self) -> ExceptionData:
        assert isinstance(self.value, ExceptionData)
        return self.value
