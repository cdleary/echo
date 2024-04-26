import csample

class MyClass: pass

assert not isinstance(MyClass, csample.CSample)
assert not isinstance(csample.CSample, MyClass)
