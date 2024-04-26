import enum


class Shape(enum.IntEnum):
    CIRCLE = 1
    SQUARE = 2


want = (Shape, enum.IntEnum, int, enum.Enum, object)
got = Shape.__mro__
assert want == got, 'want {}\ngot  {}'.format(want, got)
