"""ADT that encapsulates `interpreter_result_value | error_data`."""

from typing import TypeVar, Union, Generic, Text, Callable, Tuple, Any

import collections
import functools
from enum import Enum


T = TypeVar('T')


class ExceptionData:
    def __init__(self, traceback, parameter, exception):
        self.traceback = traceback or []
        self.parameter = parameter
        self.exception = exception

    def __repr__(self):
        return ('ExceptionData(traceback={!r}, parameter={!r}, '
                'exception={!r})'.format(
                    self.traceback, self.parameter, self.exception))


class Result(Generic[T]):
    """Represents either a value returned from execution or an exception."""

    def __init__(self, value: Union[T, ExceptionData]):
        self.value = value

    def __repr__(self) -> Text:
        return 'Result({!r})'.format(self.value)

    def __int__(self) -> None:
        raise TypeError('Call get_value() to unwrap a result.')

    def is_exception(self) -> bool:
        return isinstance(self.value, ExceptionData)

    def get_value(self) -> T:
        assert not isinstance(self.value, ExceptionData), self.value
        return self.value

    def get_exception(self) -> ExceptionData:
        assert isinstance(self.value, ExceptionData)
        return self.value


def check_result(f: Callable[..., Result]) -> Callable[..., Result]:
    """Helper decorator that checks a function returns a Result."""
    @functools.wraps(f)
    def checker(*args, **kwargs):
        assert callable(f), f
        result = f(*args, **kwargs)
        data = (f, args, kwargs, result)
        assert isinstance(result, Result), data
        if not result.is_exception():
            assert not isinstance(result.get_value(), Result), data
        return result
    return checker
