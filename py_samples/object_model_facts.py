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
