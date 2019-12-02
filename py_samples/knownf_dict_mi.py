class A(dict): pass

class B(dict): pass

class C(A, B): pass

o = C()
A.setdefault(o, 'k', 42)
assert B.__getitem__(o, 'k') == 42
