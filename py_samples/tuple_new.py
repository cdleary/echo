assert tuple.__new__(tuple) == ()



class MyTuple(tuple): pass

t = tuple.__new__(MyTuple)
assert isinstance(t, MyTuple)
assert t == ()
