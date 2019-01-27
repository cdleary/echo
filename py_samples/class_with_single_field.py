class WithSingleField:
    def __init__(self, value):
        self.value = value


a = WithSingleField('a')
b = WithSingleField('b')

assert a is not b
assert a.value == 'a'
assert b.value == 'b'
assert a.value != b.value
