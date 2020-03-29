import ctypes
import dataclasses
import types
from typing import Callable, Tuple, Type, Union

from echo.ir import bc2ir, printer
from echo.ir import typeinfer
from echo.ir import ir
from echo.cg.masm import Masm, Register


@dataclasses.dataclass
class StackLoc:
    slot: int


@dataclasses.dataclass
class Constant:
    address: int


Loc = Union[Register, StackLoc, Constant]


def paramno_to_loc(paramno: int) -> Loc:
    if paramno == 0:
        return Register.RDI
    elif paramno == 1:
        return Register.RSI
    else:
        raise NotImplementedError(paramno)


class CodeGenerator:
    """Very simple code generator for call-threaded dispatch.

    It attempts to do direct IR-to-assembly conversion, where the assembly
    simply calls the Python API routines that implement the bytecode,
    potentially specialized on deduced type.

    This is somewhat analogous to a 'baseline' code emitter in some JITs, where
    we just want to get into assembly quickly, perhaps using type information
    that can be deduced from the parameter type set.

    Generally values are homed on the stack -- for a given node to execute it
    loads its operands, performs its call, and stores its result value out to
    its corresponding stack location.

    This is not expected to be very good, but will get us experience with the
    basic perils of codegen from Python.
    """

    def __init__(self):
        self.masm = Masm()
        self.node_to_loc = {}
        self.node_to_stack_loc = {}
        self.next_slot = 0

    def get_or_create_stack_loc(self, node: ir.Node) -> StackLoc:
        if node in self.node_to_stack_loc:
            return self.node_to_stack_loc[node]
        slot = self.next_slot
        self.next_slot += 1
        result = self.node_to_stack_loc[node] = StackLoc(slot)
        return result

    def push_to_stack(self, node: ir.Node, src: Register) -> None:
        """Pushes result value for 'node', given by 'src' reg, to the stack."""
        self.node_to_loc[node] = self.node_to_stack_loc[node] \
            = StackLoc(self.next_slot)
        self.masm.pushq(src)
        self.next_slot += 1

    def spill_node_at(self, reg: Register) -> None:
        if reg not in self.node_to_loc.values():
            return
        node = next(node for node, home in self.node_to_loc.items()
                    if home == reg)
        stack_loc = self.get_or_create_stack_loc(node)
        raise NotImplementedError(reg)

    def load_to_param0(self, node: ir.Node):
        self.spill_node_at(Register.RDI)
        assert node in self.node_to_loc
        loc = self.node_to_loc[node]
        if isinstance(loc, Register):
            if loc == Register.RDI:
                return  # Already there.
        raise NotImplementedError(loc)

    def load_to_param1(self, node: ir.Node):
        self.spill_node_at(Register.RSI)
        assert node in self.node_to_loc
        loc = self.node_to_loc[node]
        if isinstance(loc, Constant):
            self.masm.movq_i64r(loc.address, Register.RSI)
        else:
            raise NotImplementedError(loc)

    def handle_node(self, node: ir.Node) -> None:
        if isinstance(node, ir.Param):
            self.node_to_loc[node] = paramno_to_loc(node.paramno)
        elif isinstance(node, ir.LoadConst):
            if isinstance(node.value, int) and node.value <= 256:
                self.node_to_loc[node] = Constant(id(node.value))
            else:
                raise NotImplementedError
        elif isinstance(node, ir.Add):
            if node.type is int:
                libpython = ctypes.CDLL('libpython3.7m.so')
                num_add = libpython.PyNumber_Add
                self.load_to_param0(node.lhs)
                self.load_to_param1(node.rhs)
                self.masm.movq_i64r(ctypes.addressof(num_add), Register.RAX)
                self.masm.callq_r(Register.RAX)
                self.push_to_stack(node, Register.RAX)
            else:
                raise NotImplementedError(node.type)
        else:
            raise NotImplementedError(node)


def compile(code: types.CodeType, arg_types: Tuple[Type, ...]) -> Callable:
    cfg = bc2ir.bytecode_to_ir(code)
    typeinfer.typeinfer(cfg, arg_types)
    print(printer.pprint_cfg(cfg))
    cg = CodeGenerator()
    cfg.walk(cg.handle_node)
    raise NotImplementedError
