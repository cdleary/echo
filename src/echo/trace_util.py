import re


def remove_at_hex(s):
    return re.sub(' at 0x[a-f0-9]+', '', s)
