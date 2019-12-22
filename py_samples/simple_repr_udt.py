class Foo: pass


# TODO(cdleary) Need builtin object.__repr__ to obey descriptor protocol for
# __get__.
o = Foo()
r = ' '.join(repr(o).split()[:-2]) + '>'
assert r == '<__main__.Foo object>', r
