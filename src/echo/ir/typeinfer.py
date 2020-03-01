from typing import Type, Tuple

from echo.ir import ir
from echo.elog import log, debugged


@debugged('ti')
def deduce(node: ir.Node, arg_types: Tuple[Type, ...]) -> Type:
    if isinstance(node, ir.LoadConst):
        return type(node.value)
    elif isinstance(node, ir.Add):
        log('ti:add', f'lhs: {node.lhs} rhs: {node.rhs}')
        assert node.lhs.type == node.rhs.type
        return node.lhs.type
    elif isinstance(node, ir.Param):
        return arg_types[node.paramno]
    else:
        raise NotImplementedError


def typeinfer(cfg: ir.Cfg, arg_types: Tuple[Type, ...]):
    def set_deduce(node: ir.Node):
        type_ = deduce(node, arg_types)
        node.type = type_

    cfg.walk(set_deduce)
