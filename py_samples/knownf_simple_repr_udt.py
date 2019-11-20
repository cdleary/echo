class Foo: pass


# TODO(cdleary) Need builtin object.__repr__ to obey descriptor protocol for
# __get__.
o = Foo()
assert repr(o) == '', repr(o)
