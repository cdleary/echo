import enum
from enum import IntEnum as _IntEnum

FOO = 42
BAR = 64
smol = 128

# This private interface changed at some point between 3.7 and 3.9.
convert = _IntEnum._convert if hasattr(_IntEnum, '_convert') else _IntEnum._convert_

converted = convert('Stuff', __name__,
                    lambda name: name.isupper())
assert converted.__name__ == 'Stuff', repr(converted)
assert converted.FOO.value == 42
assert converted.BAR.value == 64
assert hasattr(converted, 'FOO')
assert not hasattr(converted, 'smol')
