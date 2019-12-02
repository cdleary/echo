class MyClass:
    x = 42

    def f(self):
        return self.x


class OtherClass:
    x = 64



# First graft the unbound method.
OtherClass.f = MyClass.f
o = OtherClass()
assert o.f() == 64

# Then graft a bound method.
mc = MyClass()
o.f = mc.f
assert o.f() == 42
