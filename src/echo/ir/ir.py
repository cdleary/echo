from typing import Tuple, Text, Any, Dict, Union, Optional

import enum
import types


class Control:
    pass


class Node:
    def __init__(self, ssa_id: Union[int, Text], operands: Tuple['Node', ...]):
        assert isinstance(operands, tuple), operands
        assert all(isinstance(o, (Node, type(None))) for o in operands), \
            operands
        self._ssa_id = str(ssa_id) if isinstance(ssa_id, int) else ssa_id
        self.operands = operands

    @property
    def ssa_id(self) -> Text:
        return self._ssa_id

    def printable_guts(self) -> Text:
        return ', '.join(f'%{operand.ssa_id}' for operand in self.operands)


def ssa_id_or_none(n: Optional[Node]):
    return 'None' if n is None else '%' + n.ssa_id


def _is_valid_label(s: Text) -> bool:
    return 'a' <= s[0] <= 'z' and all(c.isalnum() for c in s[1:])


class Block:
    def __init__(self, label: Text):
        assert _is_valid_label(label), label
        self.nodes = []
        self.label = label
        self.control = None

    def add_node(self, node: Node) -> None:
        self.nodes.append(node)

    def add_control(self, control: Control) -> None:
        assert self.control is None
        self.control = control


class Cfg:
    def __init__(self):
        self.blocks = []
        self.dependent = {}  # type: Dict[types.CodeType, Cfg]

    def add_block(self, label: Text) -> Block:
        self.blocks.append(Block(label))
        return self.blocks[-1]


class Param(Node):
    def __init__(self, name: Text):
        super().__init__(name, ())


class LoadConst(Node):
    def __init__(self, pc: int, value: Any):
        super().__init__(pc, ())
        self.value = value

    def printable_guts(self) -> Text:
        return repr(self.value)


class LoadCfg(Node):
    def __init__(self, pc: int, cfgno: int):
        super().__init__(pc, ())
        self.cfgno = cfgno

    def printable_guts(self) -> Text:
        return repr(self.cfgno)


class LoadName(Node):
    def __init__(self, pc: int, name: Text):
        super().__init__(pc, ())
        self.name = name


class LoadGlobal(Node):
    def __init__(self, pc: int, name: Text):
        super().__init__(pc, ())
        self.name = name

    def printable_guts(self) -> Text:
        return repr(self.name)


class StoreName(Node):
    def __init__(self, pc: int, name: Text, value: Node):
        super().__init__(pc, (value,))
        self.name = name

    def printable_guts(self) -> Text:
        return f'value={ssa_id_or_none(self.value)}, name={self.name!r}'


class LoadAttr(Node):
    def __init__(self, pc: int, obj: Node, attr: Text):
        super().__init__(pc, (obj,))
        self.attr = attr

    @property
    def obj(self) -> Node:
        return self.operands[0]

    def printable_guts(self) -> Text:
        return f'obj={ssa_id_or_none(self.obj)}, attr={self.attr!r}'


class StoreAttr(Node):
    def __init__(self, pc: int, obj: Node, attr: Text, value: Node):
        super().__init__(pc, (obj, value))
        self.attr = attr

    @property
    def obj(self) -> Node:
        return self.operands[0]

    @property
    def value(self) -> Node:
        return self.operands[1]

    def printable_guts(self) -> Text:
        return (f'obj={ssa_id_or_none(self.obj)}, attr={self.attr!r}, '
                f'value={ssa_id_or_none(self.value)}')


class Add(Node):
    def __init__(self, pc: int, lhs: Node, rhs: Node):
        super().__init__(pc, (lhs, rhs))


class Mul(Node):
    def __init__(self, pc: int, lhs: Node, rhs: Node):
        super().__init__(pc, (lhs, rhs))


class ListAppend(Node):
    def __init__(self, pc: int, lhs: Node, rhs: Node):
        super().__init__(pc, (lhs, rhs))


class Comparison(enum.Enum):
    EQ = '=='


class Cmp(Node):
    def __init__(self, pc: int, op: Comparison, lhs: Node, rhs: Node):
        super().__init__(pc, (lhs, rhs))
        self.op = op


class GetIter(Node):
    def __init__(self, pc: int, arg: Node):
        super().__init__(pc, (arg,))


class Next(Node):
    def __init__(self, pc: int, arg: Node):
        super().__init__(pc, (arg,))


class BuildList(Node):
    def __init__(self, pc: int, items: Tuple[Node, ...]):
        super().__init__(pc, items)


class MakeFunction(Node):
    def __init__(self, pc: int, qualified_name: Node,
                 code: Node,
                 positional_defaults: Optional[Node],
                 kwarg_defaults: Optional[Node],
                 freevar_cells: Optional[Node]):
        assert isinstance(qualified_name, Node)
        super().__init__(pc, (qualified_name, code, positional_defaults,
                              kwarg_defaults, freevar_cells))

    @property
    def qualified_name(self) -> Node:
        return self.operands[0]

    @property
    def code(self) -> Node:
        return self.operands[1]

    @property
    def positional_defaults(self) -> Optional[Node]:
        return self.operands[2]

    @property
    def kwarg_defaults(self) -> Optional[Node]:
        return self.operands[3]

    @property
    def freevar_cells(self) -> Optional[Node]:
        return self.operands[4]

    def printable_guts(self) -> Text:
        return (
            f'qname={ssa_id_or_none(self.qualified_name)}, '
            f'code={ssa_id_or_none(self.code)}, '
            f'positional_defaults={ssa_id_or_none(self.positional_defaults)}, '
            f'kwarg_defaults={ssa_id_or_none(self.kwarg_defaults)}, '
            f'freevar_cells={ssa_id_or_none(self.freevar_cells)}')


class CallFn(Node):
    def __init__(self, pc: int, f: Node, args: Tuple[Node, ...],
                 kwargs: Dict[Text, Node]):
        super().__init__(pc, (f,) + args + tuple(kwargs.values()))
        self.kwargs = tuple(kwargs.keys())

    @property
    def fn(self) -> Node:
        op = self.operands[0]
        assert isinstance(op, Node), op
        return op

    @property
    def args(self) -> Tuple[Node, ...]:
        return self.operands[1:len(self.operands)-len(self.kwargs)]

    def printable_guts(self) -> Text:
        assert not self.kwargs
        if self.args:
            args_str = (', args=[' +
                        ', '.join(f'%{arg.ssa_id}' for arg in self.args) + ']')
        else:
            args_str = ''
        return f'%{self.fn.ssa_id}{args_str}'


class JumpOnStopIteration(Control):
    def __init__(self, value: Node, on_stop_label: Text):
        assert isinstance(value, Node), value
        self.value = value
        self.on_stop_label = on_stop_label


class JumpOnFalse(Control):
    def __init__(self, value: Node, on_false_label: Text):
        assert isinstance(value, Node), value
        self.value = value
        self.on_false_label = on_false_label


class JumpAbs(Control):
    def __init__(self, label: Text):
        self.label = label


class Return(Control):
    def __init__(self, value: Node):
        self.value = value
