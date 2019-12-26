class MyClass:
    def __getitem__(self, i):
        if i == 0: return 1
        elif i == 1: return 2
        else: raise IndexError


lst = []
lst[:] = MyClass()
assert lst == [1, 2], lst
