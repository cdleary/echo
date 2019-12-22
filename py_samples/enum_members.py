import enum


class MyFlag(enum.IntFlag):
    FOO = 256
    F = FOO


assert type(MyFlag) is enum.EnumMeta, type(MyFlag)
m = MyFlag.__members__
assert 'FOO' in m
assert 'F' in m
assert isinstance(m['FOO'], MyFlag)
assert isinstance(m['F'], MyFlag)
assert m['FOO'] is MyFlag.FOO
