import io
from typing import Text

from echo.ir import ir
from echo.common import camel_to_underscores


def _pprint_control(node: ir.Control, f: io.StringIO) -> None:
    if isinstance(node, ir.JumpAbs):
        print(f'!jump :{node.label}', file=f)
    elif isinstance(node, ir.JumpOnStopIteration):
        print(f'!jump_on_stop %{node.value.ssa_id}, :{node.on_stop_label}',
              file=f)
    elif isinstance(node, ir.JumpOnFalse):
        print(f'!jump_on_false %{node.value.ssa_id}, :{node.on_false_label}',
              file=f)
    elif isinstance(node, ir.Return):
        print(f'!return %{node.value.ssa_id}', file=f)
    else:
        raise NotImplementedError(node)


def _pprint_node(node: ir.Node, f: io.StringIO) -> None:
    name = camel_to_underscores(node.__class__.__name__)
    guts = node.printable_guts()
    print(f'%{node.ssa_id} = {name}({guts})', file=f)


def _pprint_block(b: ir.Block, f: io.StringIO) -> None:
    print(f'{b.label}:', file=f)
    for node in b.nodes:
        print(' ' * 4, file=f, end='')
        _pprint_node(node, f=f)
    print(' ' * 4, file=f, end='')
    _pprint_control(b.control, f=f)


def pprint_cfg(cfg: ir.Cfg) -> Text:
    f = io.StringIO()
    for i, block in enumerate(cfg.blocks):
        _pprint_block(block, f)
        if i+1 != len(cfg.blocks):
            print(file=f)
    return f.getvalue()
