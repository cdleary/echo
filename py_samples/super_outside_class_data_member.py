class Base:
    def __init__(self):
        self.data = 42



class Derived(Base):
    def __init__(self):
        super().__init__()
        print(super().data)


try:
    d = Derived()
except AttributeError as e:
    assert "'super' object has no attribute 'data'" in str(e)
else:
    assert False
