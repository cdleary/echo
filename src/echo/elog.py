import os
import sys
from typing import Text


ECHO_DEBUG = os.getenv('ECHO_DEBUG', '')


def log(channel: Text, s: Text):
    if not ECHO_DEBUG:
        return
    if (ECHO_DEBUG != 'all'
            and isinstance(ECHO_DEBUG, str)
            and not channel.startswith(ECHO_DEBUG)):
        return
    print(f'[{channel}] {s}', file=sys.stderr)
