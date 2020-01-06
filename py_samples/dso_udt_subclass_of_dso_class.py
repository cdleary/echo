import csample

class MyClass(csample.CSample): pass

o = object()
assert not isinstance(o, MyClass)
assert not isinstance(o, csample.CSample)
