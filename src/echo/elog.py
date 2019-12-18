import functools
import os
import sys
from typing import Text, Callable


ECHO_DEBUG = os.getenv('ECHO_DEBUG', '')


def _accepts(channel: Text) -> bool:
    if not ECHO_DEBUG:
        return False
    if ECHO_DEBUG in ('all', '1'):
        return True
    starts = ECHO_DEBUG.split(',')
    return any(channel.startswith(start) for start in starts)


def log(channel: Text, s: Text) -> None:
    ECHO_DEBUG = os.getenv('ECHO_DEBUG', '')
    if not ECHO_DEBUG:
        return
    if not _accepts(channel):
        return
    print(f'[{channel}] {s}', file=sys.stderr)


def debugged(channel: Text,
             show_start: bool = False) -> Callable[[Callable], Callable]:
    def do_debug(f: Callable) -> Callable:
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            args_str = ', '.join(repr(a) for a in args)
            kwargs_str = '' if not kwargs else ', '.join(
                '{}={!r}'.format(k, v) for k, v in kwargs.items())
            sep = ', ' if args and kwargs else ''

            if show_start:
                log(channel, '{}({}{}{}) <start>'.format(
                    f.__name__, args_str, sep, kwargs_str))
            result = f(*args, **kwargs)
            log(channel, '{}({}{}{}) => {}'.format(
                f.__name__, args_str, sep, kwargs_str, result))
            return result
        return wrapper
    return do_debug
