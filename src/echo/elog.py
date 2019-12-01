import os
import sys
from typing import Text


ECHO_DEBUG = os.getenv('ECHO_DEBUG', '')


def _accepts(channel: Text) -> bool:
    if not ECHO_DEBUG:
        return False
    if ECHO_DEBUG in ('all', '1'):
        return True
    starts = ECHO_DEBUG.split(',')
    return any(channel.startswith(start) for start in starts)


def log(channel: Text, s: Text) -> None:
    if not ECHO_DEBUG:
        return
    if not _accepts(channel):
        return
    print(f'[{channel}] {s}', file=sys.stderr)
