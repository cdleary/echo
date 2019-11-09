class Base:
    pass


class A(Base):
    pass


class B(Base):
    pass


class C(A, B):
    pass


print('Base mro:', Base.__mro__)
assert Base.__mro__ == (Base, object), Base.__mro__
print('C mro:', C.__mro__)
assert C.__mro__ == (C, A, B, Base, object), C.__mro__
