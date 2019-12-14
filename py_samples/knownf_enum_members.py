import collections
import enum


class MyFlag(enum.IntFlag):
    FOO = 256


assert type(MyFlag) is enum.EnumMeta, type(MyFlag)
assert str(MyFlag.__members__) == "OrderedDict([('FOO', <MyFlag.FOO: 256>)])"
