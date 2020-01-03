import builtins
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
memoryview bytes complex
compile
NotImplemented StopIteration
print globals abs ord chr open

NameError AttributeError KeyError TypeError IndexError ImportError
NotImplementedError ValueError AssertionError SystemError RuntimeError
MemoryError OSError FutureWarning

Warning PendingDeprecationWarning ImportWarning ResourceWarning
UserWarning DeprecationWarning RuntimeWarning
""".split())


def make_ebuiltins() -> Dict[Text, Any]:
    result = {name: get_guest_builtin(name) for name in BUILTINS}
    for name in PASSTHRU:
        result[name] = getattr(builtins, name)
    return result
