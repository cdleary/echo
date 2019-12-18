class MyClass:
    def __len__(self):
        return 42


o = MyClass()
assert len(o) == 42
