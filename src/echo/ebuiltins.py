import builtins
from typing import Dict, Text, Any

from echo.eobjects import get_guest_builtin

BUILTINS = tuple("""len str int bool super type object list dict tuple
property staticmethod classmethod
map iter next enumerate any all exec hash
hasattr getattr setattr isinstance issubclass repr callable min max dir
BaseException Exception
""".split())
PASSTHRU = tuple("""range slice float reversed set frozenset zip sorted
bytearray memoryview bytes
NotImplemented StopIteration
print globals abs ord chr
NameError AttributeError KeyError TypeError IndexError ImportError
NotImplementedError ValueError AssertionError
Warning PendingDeprecationWarning ImportWarning ResourceWarning
UserWarning DeprecationWarning""".split())


def make_ebuiltins() -> Dict[Text, Any]:
    result = {name: get_guest_builtin(name) for name in BUILTINS}
    for name in PASSTHRU:
        result[name] = getattr(builtins, name)
    return result
