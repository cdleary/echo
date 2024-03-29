# `type` is an object
assert isinstance(type, object)

# `type` is a type
assert isinstance(type, type)
assert type(type) is type

# `type` can be instantiated
assert type('T', (), {}).__class__ is type

# object is also a type
assert isinstance(object, type)

# type is a subclass of object
assert issubclass(type, object), 'type is a subclass of object'

# object has no bases
assert not object.__bases__

# None is an object.
assert isinstance(None, object)

assert (int == frozenset) is False

assert str.__module__ == 'builtins'
assert str.__name__ == 'str'
assert str.__qualname__ == 'str'

assert bool(object()) is True

assert Exception.__bases__ == (BaseException,), Exception.__bases__
assert BaseException.__bases__ == (object,), BaseException.__bases__
assert type.__bases__ == (object,), type.__bases__
