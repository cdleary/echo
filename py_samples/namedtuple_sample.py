from collections import namedtuple


MyTuple = namedtuple('MyTuple', 'foo bar baz')
assert type(MyTuple) is type, type(MyTuple)
assert MyTuple.__doc__ == 'MyTuple(foo, bar, baz)', MyTuple.__doc__

assert MyTuple(1, 2, 3) < MyTuple(2, 3, 4)
