import collections
import enum


class MyFlag(enum.IntFlag):
    FOO = 256


assert type(MyFlag) is enum.EnumMeta, type(MyFlag)
m = MyFlag.__members__
assert 'FOO' in m
assert isinstance(m['FOO'], MyFlag)
# TODO(cdleary): 2019-12-13 Needs getattr support.
#assert m['FOO'] is MyFlag.FOO
