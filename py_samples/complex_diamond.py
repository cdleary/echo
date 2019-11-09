class I: pass
class E(I): pass
class F: pass
class G: pass
class H: pass
class B(E, F): pass
class C(F, G): pass
class D(G, H): pass
class A(B, C, D): pass


assert A.__mro__ == (A, B, E, I, C, F, D, G, H, object), A.__mro__
