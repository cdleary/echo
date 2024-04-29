"""Commonly used utility functions."""

import dis
import functools
import types
from typing import (
    Any, Text, Sequence, Tuple, List, TypeVar, Callable, Dict
)
from io import StringIO


T = TypeVar('T')


def get_code(x: Any) -> types.CodeType:
    return x.__code__


def dis_to_str(x: Any) -> Text:
    out = StringIO()
    dis.dis(x, file=out)
    return out.getvalue()


def memoize(f: Callable[..., T]) -> Callable[..., T]:
    cache: Dict[Tuple, Any] = {}

    @functools.wraps(f)
    def wrapper(*args):
        if args in cache:
            return cache[args]
        result = f(*args)
        cache[args] = result
        return result

    return wrapper


def none_filler(it: Sequence[Any], count: int) -> Tuple[Any, ...]:
    return tuple(it) + tuple(None for _ in range(count-len(it)))


def camel_to_underscores(s: str) -> str:
    pieces: List[str] = []
    for letter in s:
        if letter.isupper() and pieces:
            pieces.append('_')
        pieces.append(letter.lower())
    return ''.join(pieces)
