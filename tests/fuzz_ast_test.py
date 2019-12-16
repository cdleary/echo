from echo.fuzz.genseq import Stmt, Expr, Suite, NameDef, As


def test_assign_stmt():
    x = NameDef('x')
    s0 = Stmt.make_assign(x, Expr.make_dict_literal())
    y = NameDef('y')
    s1 = Stmt.make_assign(y, Expr.make_dict_literal())
    s2 = Stmt.make_expr(
        Expr.make_invoke(
            Expr.make_getattr(Expr.make_name_ref(x), 'update'),
            (Expr.make_name_ref(y),)))
    b = Suite((s0, s1, s2))
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
    b = Suite((s0, s1))
    assert b.format() == """\
class MyClass:
    pass
o = MyClass()
"""


def test_if_stmt():
    test = Expr.make_none()
    assert test.format() == 'None'
    print_def = NameDef('print')
    print_expr = Expr.make_invoke(Expr.make_name_ref(print_def),
                                  (Expr.make_str('yay'),))
    consequent = Suite([Stmt.make_expr(print_expr)])
    stmt = Stmt.make_if(test, consequent, (), None)
    assert stmt.format() == """\
if None:
    print('yay')
"""


def test_try_stmt():
    pass_ = Stmt.make_pass()
    pass_suite = Suite([pass_])
    exception_def = NameDef('Exception')
    except_clause = As(Expr.make_name_ref(exception_def), NameDef('e'))
    stmt = Stmt.make_try(pass_suite, [(except_clause, pass_suite)], pass_suite)
    assert stmt.format() == """\
try:
    pass
except Exception as e:
    pass
finally:
    pass
"""
