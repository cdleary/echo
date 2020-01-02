class MyClass:
    def __init__(self):
        self._value = None

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value


assert isinstance(MyClass.value, property)
o = MyClass()
assert 'value' not in o.__dict__
assert o.value == None
o.value = 42
assert 'value' not in o.__dict__, 'did not set via descriptor'
assert o.value == 42
assert o._value == 42
