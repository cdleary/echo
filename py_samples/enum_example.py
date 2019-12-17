import enum


class MyEnum(enum.Enum):
    FOO = 1
    BAR = 2


assert MyEnum.FOO.value == 1
assert MyEnum.BAR.value == 2
assert MyEnum.__mro__ == (MyEnum, enum.Enum, object), MyEnum.__mro__
