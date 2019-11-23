from echo.fuzz.genseq import Statement, Expr, Block, NameDef


def test_assign_stmt():
    x = NameDef('x')
    s0 = Statement.make_assign(x, Expr.make_dict_literal())
    y = NameDef('y')
    s1 = Statement.make_assign(y, Expr.make_dict_literal())
    s2 = Statement.make_expr(Expr.make_invoke(Expr.make_name_ref(x), 'update',
                             Expr.make_name_ref(y)))
    b = Block((s0, s1, s2))
    assert b.format() == """\
x = {}
y = {}
x.update(y)"""
