# Derived from https://bugs.python.org/file36760/function-documentation.patch


class MyObject(object): pass
assert MyObject.__base__ is object

class Derived(MyObject): pass
assert Derived.__base__ is MyObject

class MyInt(int): pass
assert MyInt.__base__ is int

class Candidate(Derived, MyObject, MyInt): pass
assert Candidate.__base__ is MyInt

class Candidate(Derived, MyObject, int): pass
assert Candidate.__base__ is int

class Candidate(Derived, MyObject): pass
assert Candidate.__base__ is Derived
