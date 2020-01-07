from enum import IntEnum as _IntEnum

FOO = 42
BAR = 64

_IntEnum._convert('Stuff', __name__,
                  lambda name: name.isupper())
