class MyClass:
    def __init__(self):
        self.foo = 42
        self.bar = 'some str'


o = MyClass()
assert vars(o) == dict(foo=42, bar='some str'), vars(o)


def main():
    foo = 64
    assert vars() == dict(foo=64)


main()
