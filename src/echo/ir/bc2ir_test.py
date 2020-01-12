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
