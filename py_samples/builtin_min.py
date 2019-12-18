assert min(0, -1) == -1
assert min('', 'abc') == ''

class MyInt(int): pass
assert min(MyInt(), -1) == -1
