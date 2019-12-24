"""Commonly used utility functions."""

import dis
import itertools
import functools
import types
from typing import Any, Text, Iterable, Sequence, Tuple
from io import StringIO


def get_code(x: Any) -> types.CodeType:
    return x.__code__


def dis_to_str(x: Any) -> Text:
    out = StringIO()
    dis.dis(x, file=out)
    return out.getvalue()


def memoize(f):
    cache = {}

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
