class Foo:
    pass


o = Foo()

assert hasattr(o, '__class__')
assert o.__class__ is Foo
assert hasattr(Foo, '__class__')
assert Foo.__class__ is type
assert '__class__' in dir(o), dir(o)

# o's dictionary is empty.
assert o.__dict__ == {}

assert Foo.__module__ == '__main__'
assert o.__module__ == '__main__'
assert '__module__' in dir(o), dir(o)
assert '__dict__' in dir(o), dir(o)

assert '__name__' not in dir(Foo)
assert '__name__' not in dir(o)
