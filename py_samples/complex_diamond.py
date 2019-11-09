class I: pass             # noqa
class E(I): pass          # noqa
class F: pass             # noqa
class G: pass             # noqa
class H: pass             # noqa
class B(E, F): pass       # noqa
class C(F, G): pass       # noqa
class D(G, H): pass       # noqa
class A(B, C, D): pass    # noqa


assert A.__mro__ == (A, B, E, I, C, F, D, G, H, object), A.__mro__
