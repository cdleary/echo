def f(): yield

gentype = type(f())
b = b'abc'
byteitertype = type(iter(b))

assert not issubclass(gentype, byteitertype)
assert not issubclass(dict, set)
