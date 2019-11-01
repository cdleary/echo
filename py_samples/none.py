assert None is None  # Singleton.
assert not isinstance(None, type)
assert type(None).__name__ == 'NoneType'
assert type(type(None)) is type, type(type(None))
assert isinstance(None, type(None))
assert isinstance(type(None), type)
