class Foo:
    @property
    def stuff(self):
        return 42


foo = Foo()
print(foo.stuff)
# TODO(cdleary) This breaks stack depth expectations.
# print(Foo.stuff.__get__)
assert isinstance(foo.stuff, int), foo.stuff
assert foo.stuff == 42
