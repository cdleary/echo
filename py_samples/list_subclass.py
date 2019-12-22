class MyList(list): pass


assert MyList.__mro__ == (MyList, list, object), MyList.__mro__
d = MyList([1, 2, 3])
assert isinstance(d, MyList), type(d)
assert issubclass(MyList, list)
d.append(42)
assert d == [1, 2, 3, 42]
d.clear()
assert d == []
d.extend([64, 128])
assert d == [64, 128]

assert 64 in d, d
assert 128 in d, d
assert 256 not in d, d

assert list(d) == [64, 128]
assert tuple(d) == (64, 128)
