from typing import Tuple, Text, Any, Dict

import enum


class Control:
    pass


class Node:
    def __init__(self, pc: int, operands: Tuple['Node', ...]):
        assert isinstance(operands, tuple), operands
        assert all(isinstance(o, Node) for o in operands), operands
        self.pc = pc
        self.operands = operands

    def printable_guts(self) -> Text:
        return ', '.join(f'%{operand.pc}' for operand in self.operands)


def _is_valid_label(s: Text) -> bool:
    return 'a' <= s[0] <= 'z' and all(c.isalnum() for c in s[1:])


class Block:
    def __init__(self, label: Text):
        assert _is_valid_label(label), label
        self.nodes = []
        self.label = label
        self.control = None

    def add_node(self, node: Node):
        self.nodes.append(node)

    def add_control(self, control: Control):
        assert self.control is None
        self.control = control


class Cfg:
    def __init__(self):
        self.blocks = []

    def add_block(self, label: Text) -> Block:
        self.blocks.append(Block(label))
        return self.blocks[-1]


class LoadConst(Node):
    def __init__(self, pc: int, value: Any):
        super().__init__(pc, ())
        self.value = value

    def printable_guts(self) -> Text:
        return repr(self.value)


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


class Add(Node):
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
                        ', '.join(f'%{arg.pc}' for arg in self.args) + ']')
        else:
            args_str = ''
        return f'%{self.fn.pc}{args_str}'


class JumpOnStopIteration(Control):
    def __init__(self, value: Node, on_stop_label: Text):
        assert isinstance(value, Node), value
        self.value = value
        self.on_stop_label = on_stop_label


class JumpAbs(Control):
    def __init__(self, label: Text):
        self.label = label


class Return(Control):
    def __init__(self, value: Node):
        self.value = value
