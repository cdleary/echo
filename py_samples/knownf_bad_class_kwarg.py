try:
    class Foo(m=2):
        pass
except TypeError as e:
    assert '__init_subclass__() takes no keyword arguments' == str(e)
else:
    assert False
