from collections import namedtuple


MyTuple = namedtuple('MyTuple', 'foo bar baz')
assert type(MyTuple) is type, type(MyTuple)
assert MyTuple.__doc__ == 'MyTuple(foo, bar, baz)', MyTuple.__doc__

assert MyTuple(1, 2, 3) < MyTuple(2, 3, 4)

t = MyTuple('foo', 42, object())
assert t[0] == 'foo'
assert t[0] == t.foo

assert t[1] == 42
assert t.bar == 42
