from echo.ir.bc2ir import bytecode_to_ir
from echo.ir import printer as ir_printer


def test_range_pass():
    def f():
        for i in range(4):
            pass

    cfg = bytecode_to_ir(f.__code__)
    got = ir_printer.pprint_cfg(cfg)
    print(got)
    want = """\
bc0:
    %2 = load_global('range')
    %4 = load_const(4)
    %6 = call_fn(%2, args=[%4])
    %8 = get_iter(%6)
    !jump :bc10

bc10:
    %10 = next(%8)
    !jump_on_stop %10, :bc16

bc12:
    !jump :bc10

bc16:
    !jump :bc18

bc18:
    %18 = load_const(None)
    !return %18
"""
    assert want == got


def test_str_ne():
    def f(x, y):
        if x != y:
            return 42
        return 64

    cfg = bytecode_to_ir(f.__code__)
    got = ir_printer.pprint_cfg(cfg)
    print(got)
    want = """\
bc0:
    %4 = cmp(%x, %y)
    !jump_on_false %4, :bc12

bc8:
    %8 = load_const(42)
    !return %8

bc12:
    %12 = load_const(64)
    !return %12
"""
    assert want == got


def test_list_comprehension():
    def f(x):
        return [list(x) for x in [x]*7]

    cfg = bytecode_to_ir(f.__code__)
    got = ir_printer.pprint_cfg(cfg)
    print(got)
    want = """\
bc0:
    %0 = load_cfg(0)
    %2 = load_const('test_list_comprehension.<locals>.f.<locals>.<listcomp>')
    %4 = make_function(qname=%2, code=%0, positional_defaults=None, kwarg_defaults=None, freevar_cells=None)
    %8 = build_list(%x)
    %10 = load_const(7)
    %12 = mul(%8, %10)
    %14 = get_iter(%12)
    %16 = call_fn(%4, args=[%14])
    !return %16
"""  # noqa
    assert want == got


def test_load_attr():
    def f(o):
        return o.attr

    cfg = bytecode_to_ir(f.__code__)
    got = ir_printer.pprint_cfg(cfg)
    print(got)
    want = """\
bc0:
    %2 = load_attr(obj=%o, attr='attr')
    !return %2
"""
    assert want == got
