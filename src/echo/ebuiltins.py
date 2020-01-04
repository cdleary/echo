import builtins
import sys
from typing import Dict, Text, Any

from echo.eobjects import get_guest_builtin

BUILTINS = tuple("""len str int bool super type object list dict tuple
bytearray
property staticmethod classmethod sum
map iter next enumerate any all exec hash vars
hasattr getattr setattr isinstance issubclass repr callable min max dir
BaseException Exception
""".split())
PASSTHRU = tuple("""range slice float reversed set frozenset zip sorted
memoryview bytes complex id
compile
NotImplemented StopIteration
print globals abs ord chr open

NameError AttributeError KeyError TypeError IndexError ImportError
NotImplementedError ValueError AssertionError SystemError RuntimeError
MemoryError OSError FutureWarning

Warning PendingDeprecationWarning ImportWarning ResourceWarning
UserWarning DeprecationWarning RuntimeWarning
""".split())

# Types that hold pyobjects.
BUILTIN_CONTAINER_TYPES = {
    dict,
    list,
    set,
    tuple,
}
BUILTIN_CONTAINER_TYPES_TUP = tuple(BUILTIN_CONTAINER_TYPES)
BUILTIN_VALUE_TYPES = {
    bool,
    bytearray,
    bytes,
    complex,
    float,
    int,
    range,
    slice,
    str,
    type(None),
    type(sys.version_info),
} | BUILTIN_CONTAINER_TYPES
BUILTIN_VALUE_TYPES_TUP = tuple(BUILTIN_VALUE_TYPES)

TYPE_TO_EBUILTIN = {
    bool: get_guest_builtin('bool'),
    bytearray: get_guest_builtin('bytearray'),
    dict: get_guest_builtin('dict'),
    int: get_guest_builtin('int'),
    list: get_guest_builtin('list'),
    object: get_guest_builtin('object'),
    set: get_guest_builtin('set'),
    str: get_guest_builtin('str'),
    tuple: get_guest_builtin('tuple'),
    type: get_guest_builtin('type'),
}


def make_ebuiltins() -> Dict[Text, Any]:
    result = {name: get_guest_builtin(name) for name in BUILTINS}
    for name in PASSTHRU:
        result[name] = getattr(builtins, name)
    return result
