from echo.fuzz.genseq import Stmt, Expr, Block, NameDef


def test_assign_stmt():
    x = NameDef('x')
    s0 = Stmt.make_assign(x, Expr.make_dict_literal())
    y = NameDef('y')
    s1 = Stmt.make_assign(y, Expr.make_dict_literal())
    s2 = Stmt.make_expr(
        Expr.make_invoke(
            Expr.make_getattr(Expr.make_name_ref(x), 'update'),
            (Expr.make_name_ref(y),)))
    b = Block((s0, s1, s2))
    assert b.format() == """\
x = {}
y = {}
(x).update(y)
"""


def test_fn_stmt():
    s0 = Stmt.make_fn_def(NameDef('my_func'), (), (
        Stmt.make_return(Expr.make_none()),
    ))
    assert s0.format() == """\
def my_func():
    return None
"""


def test_class_stmt():
    s0 = Stmt.make_class_def(NameDef('MyClass'), (
        Stmt.make_fn_def(NameDef('my_func'), (NameDef('self'),), (
            Stmt.make_return(Expr.make_none()),
        )),
    ))
    assert s0.format() == """\
class MyClass:
    def my_func(self):
        return None
"""


def test_invoke_class():
    mc = NameDef('MyClass')
    s0 = Stmt.make_class_def(mc, (Stmt.make_pass(),))
    s1 = Stmt.make_assign(NameDef('o'),
                          Expr.make_invoke(Expr.make_name_ref(mc), ()))
    b = Block((s0, s1))
    assert b.format() == """\
class MyClass:
    pass
o = MyClass()
"""
