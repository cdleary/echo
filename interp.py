"""(Metacircular) interpreter loop implementation.

Notes
-----

co_flags:

* 0x04: function uses *args
* 0x08: function uses **kwargs
* 0x20: generator function
"""

import abc
import builtins
import collections
import dis
import functools
import itertools
import logging
import operator
import os
import types
import sys

from enum import Enum
from io import StringIO
from typing import (Dict, Any, Text, Tuple, List, Optional, Union, Sequence,
                    Iterable, cast)

from common import dis_to_str, get_code
from interp_result import Result, ExceptionData
import import_routines
from arg_resolver import resolve_args, CodeAttributes
from interpreter_state import InterpreterState
from guest_objects import (GuestModule, GuestFunction, GuestInstance,
                           GuestBuiltin, GuestPyObject, GuestPartial,
                           GuestClass, GuestCell, GuestMethod)
import bytecode_trace

import termcolor


TRACE_DUMPER = bytecode_trace.FakeTraceDumper()
_GLOBAL_BYTECODE_COUNT = 0
COLOR_TRACE_FUNC = False
COLOR_TRACE_STACK = False
COLOR_TRACE_MOD = False
COLOR_TRACE = False
_BINARY_OPS = {
    'BINARY_LSHIFT': operator.lshift,
    'BINARY_ADD': operator.add,
    'BINARY_MODULO': operator.mod,
    'BINARY_MULTIPLY': operator.mul,
    'BINARY_SUBTRACT': operator.sub,
    'BINARY_SUBSCR': operator.getitem,
    'BINARY_TRUE_DIVIDE': operator.truediv,
}
_BUILTIN_VALUE_TYPES = {
    int,
    str,
    type(None),
}
_BUILTIN_VALUE_TYPES_TUP = tuple(_BUILTIN_VALUE_TYPES)
_CODE_ATTRS = [
    'co_argcount', 'co_cellvars', 'co_code', 'co_consts', 'co_filename',
    'co_firstlineno', 'co_flags', 'co_freevars', 'co_kwonlyargcount',
    'co_lnotab', 'co_name', 'co_names', 'co_nlocals', 'co_stacksize',
    'co_varnames',
]
_COMPARE_OPS = {
    '==': operator.eq,
    '!=': operator.ne,
    '<': operator.lt,
    '>': operator.gt,
    '>=': operator.ge,
    'is not': operator.is_not,
    'is': operator.is_,
    'in': lambda a, b: operator.contains(b, a),
}
_GUEST_BUILTINS = {
    list: {'append', 'remove', 'insert'},
    dict: {'keys', 'values', 'items'},
    str: {'format'},
}
_BUILTIN_EXCEPTION_TYPES = (
    AssertionError,
    AttributeError,
    ImportError,
    NameError,
    NotImplementedError,
    ValueError,
)


# Use a sentinel value (this class object) to indicate when
# UnboundLocalErrors have occurred.
class UnboundLocalSentinel:
    pass


def is_false(v: Any) -> bool:
    if isinstance(v, int):
        return v == 0
    if isinstance(v, bool):
        return v is False
    if isinstance(v, str):
        return not v
    if v is None:
        return False
    raise NotImplementedError(v)


def is_true(v: Any) -> bool:
    return not is_false(v)


def code_to_str(c: types.CodeType) -> Text:
    guts = ', '.join('{}={!r}'.format(attr.split('_')[1], getattr(c, attr))
                     for attr in _CODE_ATTRS)
    return 'Code({})'.format(guts)


def builtins_get(builtins: Union[types.ModuleType, Dict], name: Text) -> Any:
    if name in ('isinstance', 'issubclass', 'super', 'iter', 'type', 'zip',
                'reversed', 'set'):
        return GuestBuiltin(name, None)
    if isinstance(builtins, types.ModuleType):
        return getattr(builtins, name)
    return builtins[name]


def cprint(msg, color, file=sys.stderr, end='\n'):
    termcolor.cprint(msg, color=color, file=file, end=end)


def cprint_lines_after(filename: Text, lineno: int):
    with open(filename) as f:
        lines = f.readlines()
    lines = lines[lineno-1:]
    saw_def = False
    for lineno, line in enumerate(lines, lineno-1):
        # TODO(cdleary, 2019-01-24): Should detect the original indent level
        # and terminate the line printout at the first point where the indent
        # decreases (first dedent).
        if line.startswith('def'):
            if saw_def:
                break
            else:
                saw_def = True
        cprint('%05d: ' % lineno, color='yellow', end='')
        cprint(line.rstrip(), color='blue')


def _run_binop(opname: Text, lhs: Any, rhs: Any, interp) -> Result[Any]:
    if (opname in ('BINARY_TRUE_DIVIDE', 'BINARY_MODULO') and type(rhs) is int
            and rhs == 0):
        raise NotImplementedError(opname, lhs, rhs)
    if {type(lhs), type(rhs)} <= _BUILTIN_VALUE_TYPES or (
            type(lhs) in (list, dict) and opname == 'BINARY_SUBSCR') or (
            type(lhs) == type(rhs) == list and opname == 'BINARY_ADD') or (
            type(lhs) == type(rhs) == set and opname == 'BINARY_SUBTRACT') or (
            type(lhs) is str and opname == 'BINARY_MODULO'):
        op = _BINARY_OPS[opname]
        return Result(op(lhs, rhs))

    if opname == 'BINARY_SUBTRACT' and isinstance(lhs, GuestInstance):
        sub_f = lhs.getattr('__sub__')
        if sub_f.is_exception():
            raise NotImplementedError(sub_f)
        return sub_f.get_value().invoke(args=(rhs,), kwargs=None,
                                        interp=interp)

    raise NotImplementedError(opname, lhs, rhs)


def _exception_match(lhs, rhs) -> bool:
    if set([lhs, rhs]) <= set(_BUILTIN_EXCEPTION_TYPES):
        return issubclass(lhs, rhs)
    if isinstance(lhs, rhs):
        return True
    raise NotImplementedError(lhs, rhs)


def _compare(opname, lhs, rhs) -> Result[bool]:
    if (isinstance(lhs, _BUILTIN_VALUE_TYPES_TUP)
            and isinstance(rhs, _BUILTIN_VALUE_TYPES_TUP)):
        return Result(_COMPARE_OPS[opname](lhs, rhs))
    if {type(lhs), type(rhs)} == {str, tuple} and opname == '==':
        return Result(False)
    if {type(lhs), type(rhs)} == {int, tuple} and opname == '==':
        return Result(False)
    if (isinstance(lhs, (list, tuple)) and isinstance(rhs, (list, tuple))
            and opname == '=='):
        if len(lhs) != len(rhs):
            return Result(False)
        for e, f in zip(lhs, rhs):
            e_result = _compare(opname, e, f)
            if e_result.is_exception():
                return e_result
            if not e_result.get_value():
                return Result(False)
        return Result(True)
    if opname in ('in', 'not in') and type(rhs) in (
            tuple, list, dict, type(os.environ)):
        for e in rhs:
            e_result = _compare('==', lhs, e)
            if e_result.is_exception():
                return e_result
            if e_result.get_value():
                return Result(opname == 'in')
        return Result(opname == 'not in')
    if opname in ('is', 'is not'):
        if (isinstance(lhs, (GuestInstance, GuestClass)) and
                isinstance(rhs, (GuestInstance, GuestClass))):
            op = _COMPARE_OPS[opname]
            return Result(op(lhs, rhs))

    def is_set_of_strings(x):
        return isinstance(x, set) and all(isinstance(e, str) for e in x)

    if is_set_of_strings(lhs) and is_set_of_strings(rhs):
        return Result(lhs == rhs)

    raise NotImplementedError(opname, lhs, rhs)


def _method_requires_self(obj, value) -> bool:
    obj_is_module = isinstance(obj, GuestModule)
    if isinstance(value, GuestBuiltin) and value.bound_self is None:
        return not obj_is_module
    if isinstance(value, types.MethodType):
        return False
    if isinstance(value, GuestFunction):
        return not obj_is_module
    return False


class BlockKind(Enum):
    EXCEPT_HANDLER = 'EXCEPT_HANDLER'
    SETUP_LOOP = 'SETUP_LOOP'
    SETUP_EXCEPT = 'SETUP_EXCEPT'
    SETUP_FINALLY = 'SETUP_FINALLY'


class BlockInfo:
    def __init__(self, kind: BlockKind, handler: int, level: int):
        self.kind = kind
        self.handler = handler
        self.level = level

    def __repr__(self) -> Text:
        return 'BlockInfo(kind={!r}, handler={!r}, level={!r})'.format(
            self.kind, self.handler, self.level)

    def to_trace(self) -> bytecode_trace.BlockStackEntry:
        return bytecode_trace.BlockStackEntry(self.kind.value, self.handler,
                                              self.level)


class StatefulFrame:
    """A frame is the context in which some code executes.

    This StatefulFrame keeps track of the execution context for a piece of
    code; this is useful for frames that do not run to completion; e.g.
    generators, which may yield to the counter from some program counter and
    are subsequently available available to resume later.
    """

    def __init__(self,
                 code: types.CodeType,
                 pc_to_instruction: List[Optional[dis.Instruction]],
                 pc_to_bc_width: List[Optional[int]],
                 locals_: List[Any],
                 locals_dict: Dict[Text, Any],
                 globals_: Dict[Text, Any],
                 cellvars: Tuple[GuestCell, ...],
                 interpreter_state: InterpreterState,
                 in_function: bool):
        self.code = code
        self.pc = 0
        self.stack = []
        self.block_stack = []  # type: List[BlockInfo]
        self.pc_to_instruction = pc_to_instruction
        self.pc_to_bc_width = pc_to_bc_width
        self.locals_ = locals_
        self.locals_dict = locals_dict
        self.globals_ = globals_
        self.exception_data = None  # type: Optional[ExceptionData]
        self.handling_exception_data = None  # type: Optional[ExceptionData]
        self.cellvars = cellvars
        self.consts = code.co_consts
        self.names = code.co_names
        self.interpreter_state = interpreter_state
        self.in_function = in_function

        # TODO(cdleary, 2019-01-21): Investigate why this "builtins" ref is
        # sometimes a dict and other times a module?
        self.builtins = sys.modules['builtins']  # globals_['__builtins__']

        self.interp_callback = functools.partial(
            interp, state=interpreter_state)
        self.do_call_callback = functools.partial(
            do_call, state=interpreter_state)

    def _handle_exception(self):
        """Returns whether the exception was handled in this function."""
        if COLOR_TRACE:
            cprint(' ! handling exception with block stack %r; %r' % (
                    self.block_stack, self.exception_data), color='magenta')
        while (self.block_stack and
               self.block_stack[-1].kind != BlockKind.SETUP_EXCEPT):
            self.block_stack.pop()
        if (self.block_stack and
                self.block_stack[-1].kind == BlockKind.SETUP_EXCEPT):
            self.pc = self.block_stack[-1].handler
            if COLOR_TRACE:
                cprint(' ! moved PC to %d' % self.pc, color='magenta')
            while len(self.stack) > self.block_stack[-1].level:
                self._pop()
            assert isinstance(self.exception_data, ExceptionData)
            self._push(self.exception_data.traceback)
            self._push(self.exception_data.exception)
            self._push(self.exception_data.exception)
            self.block_stack[-1].kind = BlockKind.EXCEPT_HANDLER
            self.block_stack[-1].handler = -1
            self.handling_exception_data, self.exception_data = (
                self.exception_data, None)
            return True
        elif not any(entry.kind == BlockKind.SETUP_EXCEPT
                     for entry in self.block_stack):
            return False  # Definitely unhandled.
        else:
            # Need to pop block stack entries appropriately, then handle the
            # exception.
            raise NotImplementedError(self.block_stack)

    def _push(self, x):
        if COLOR_TRACE_STACK:
            cprint(' =(push)=> %r [depth after: %d]' %
                   (x, len(self.stack)+1), color='blue')
        assert not isinstance(x, Result), x
        # If the user can observe the real isinstance they can break the
        # virtualization abstraction, which is undesirable.
        assert x is not isinstance
        self.stack.append(x)

    def _pop(self):
        x = self.stack.pop()
        if COLOR_TRACE_STACK:
            cprint(' <=(pop)= %r [depth after: %d]' %
                   (x, len(self.stack)), color='blue')
        return x

    def _pop_n(self, n: int, tos_is_0: bool = True) -> Tuple[Any, ...]:
        self.stack, result = (
            self.stack[:len(self.stack)-n], self.stack[len(self.stack)-n:])
        if tos_is_0:
            return tuple(reversed(result))
        return tuple(result)

    def _peek(self):
        return self.stack[-1]

    def _get_global_or_builtin(self, name: Text) -> Any:
        try:
            return self.globals_[name]
        except KeyError:
            pass
        return builtins_get(self.builtins, name)

    def _run_POP_TOP(self, arg, argval):
        self._pop()

    def _run_LIST_APPEND(self, arg, argval):
        tos = self._pop()
        tos_mi = self.stack[-arg]
        list.append(tos_mi, tos)

    def _run_POP_BLOCK(self, arg, argval):
        self.block_stack.pop()

    def _run_DELETE_SUBSCR(self, arg, argval):
        tos = self._pop()
        tos1 = self._pop()
        if isinstance(tos1, dict):
            del tos1[tos]
        elif isinstance(tos1, GuestPyObject):
            tos1.delattr(tos)
        else:
            raise NotImplementedError(tos, tos1)

    def _run_LOAD_CONST(self, arg, argval):
        return Result(self.consts[arg])

    def _run_GET_ITER(self, arg, argval):
        return Result(self._pop().__iter__())

    def _run_LOAD_BUILD_CLASS(self, arg, argval):
        return Result(GuestBuiltin('__build_class__', None))

    def _run_BUILD_TUPLE(self, arg, argval):
        count = arg
        t = self._pop_n(count, tos_is_0=False)
        return Result(t)

    def _run_BUILD_TUPLE_UNPACK(self, arg, argval):
        iterables = self._pop_n(arg, tos_is_0=False)
        return Result(tuple(itertools.chain(*iterables)))

    def _run_BUILD_LIST(self, arg, argval):
        count = arg
        limit = len(self.stack)-count
        self.stack, t = self.stack[:limit], self.stack[limit:]
        return Result(t)

    def _run_BUILD_MAP(self, arg, argval):
        items = self._pop_n(2 * arg, tos_is_0=False)
        ks = items[::2]
        vs = items[1::2]
        return Result(dict(zip(ks, vs)))

    def _run_BUILD_SET(self, arg, argval):
        count = arg
        limit = len(self.stack)-count
        self.stack, t = self.stack[:limit], self.stack[limit:]
        return Result(set(t))

    def _run_BUILD_CONST_KEY_MAP(self, arg, argval):
        count = arg
        ks = self._pop()
        self.stack, vs = self.stack[:-count], tuple(self.stack[-count:])
        assert len(ks) == len(vs)
        return Result(dict(zip(ks, vs)))

    def _run_ROT_TWO(self, arg, argval):
        self.stack[-1], self.stack[-2] = self.stack[-2], self.stack[-1]

    def _run_DUP_TOP(self, arg, argval):
        assert self.stack, 'Cannot DUP_TOP of empty stack.'
        self.stack = self.stack + self.stack[-1:]

    def _run_POP_EXCEPT(self, arg, argval):
        if COLOR_TRACE:
            cprint(' ! popping except with block stack %r' % self.block_stack,
                   color='magenta')
        popped = self.block_stack.pop()
        assert popped.kind in (BlockKind.SETUP_EXCEPT,
                               BlockKind.EXCEPT_HANDLER), (
            'Popped non-except block.', popped)

    def _run_SETUP_FINALLY(self, arg, argval):
        # "Pushes a try block from a try-except clause onto the block stack.
        # delta points to the finally block."
        # -- https://docs.python.org/3.7/library/dis.html#opcode-SETUP_FINALLY
        self.block_stack.append(BlockInfo(
            BlockKind.SETUP_FINALLY, arg+self.pc+self.pc_to_bc_width[self.pc],
            len(self.stack)))

    def _run_DELETE_NAME(self, arg, argval):
        if self.in_function:
            self.locals_[arg] = UnboundLocalSentinel
        else:
            del self.globals_[argval]

    def _run_DUP_TOP_TWO(self, arg, argval):
        self.stack = self.stack + self.stack[-2:]

    def _run_ROT_THREE(self, arg, argval):
        #                                  old first  old second  old third
        self.stack[-3], self.stack[-1], self.stack[-2] = (
            self.stack[-1], self.stack[-2], self.stack[-3])

    def _run_LOAD_DEREF(self, arg, argval):
        return Result(self.cellvars[arg].get())

    def _run_STORE_DEREF(self, arg, argval):
        self.cellvars[arg].set(self._pop())

    def _run_STORE_FAST(self, arg, argval):
        self.locals_[arg] = self._pop()

    def _run_LOAD_CLOSURE(self, arg, argval):
        return Result(self.cellvars[arg])

    def sets_pc(f):
        f._sets_pc = True
        return f

    @sets_pc
    def _run_BREAK_LOOP(self, arg, argval):
        loop_block = self.block_stack[-1]
        assert loop_block.kind == BlockKind.SETUP_LOOP
        self.pc = loop_block.handler
        return True

    @sets_pc
    def _run_JUMP_ABSOLUTE(self, arg, argval):
        self.pc = arg
        return True

    @sets_pc
    def _run_JUMP_FORWARD(self, arg, argval):
        self.pc += arg + self.pc_to_bc_width[self.pc]
        return True

    @sets_pc
    def _run_POP_JUMP_IF_FALSE(self, arg, argval):
        if is_false(self._pop()):
            self.pc = arg
            return True
        return False

    @sets_pc
    def _run_POP_JUMP_IF_TRUE(self, arg, argval):
        if is_true(self._pop()):
            self.pc = arg
            return True
        return False

    @sets_pc
    def _run_JUMP_IF_FALSE_OR_POP(self, arg, argval):
        if is_false(self._peek()):
            pc = arg
            return True
        else:
            self._pop()
            return False

    @sets_pc
    def _run_FOR_ITER(self, arg, argval):
        try:
            x = self._peek().__next__()
        except StopIteration:
            self._pop()
            self.pc += self.pc_to_bc_width[self.pc] + arg
            new_instruction = self.pc_to_instruction[self.pc]
            assert new_instruction is not None
            assert new_instruction.is_jump_target, (
                'Attempted to jump to invalid target.', self.pc,
                self.pc_to_instruction[self.pc])
            return True
        else:
            self._push(x)
            return False

    def _run_MAKE_FUNCTION(self, arg, argval):
        if sys.version_info >= (3, 6):
            qualified_name = self._pop()
            code = self._pop()
            freevar_cells = self._pop() if arg & 0x08 else None
            annotation_dict = self._pop() if arg & 0x04 else None
            kwarg_defaults = self._pop() if arg & 0x02 else None
            positional_defaults = self._pop() if arg & 0x01 else None
            if annotation_dict:
                raise NotImplementedError(annotation_dict)
        else:
            # 3.5 documentation:
            # https://docs.python.org/3.5/library/dis.html#opcode-MAKE_FUNCTION
            default_argc = arg & 0xff
            name_and_default_pairs = (arg >> 8) & 0xff
            annotation_objects = (arg >> 16) & 0x7fff
            if annotation_objects:
                raise NotImplementedError(annotation_objects)
            qualified_name = self._pop()
            code = self._pop()
            kwarg_default_items = self._pop_n(2 * name_and_default_pairs,
                                              tos_is_0=False)
            kwarg_defaults = dict(zip(kwarg_default_items[::2],
                                      kwarg_default_items[1::2]))
            positional_defaults = self._pop_n(default_argc, tos_is_0=False)
            freevar_cells = None

        f = GuestFunction(code, self.globals_, qualified_name,
                          defaults=positional_defaults,
                          kwarg_defaults=kwarg_defaults, closure=freevar_cells)
        return Result(f)

    def _run_CALL_FUNCTION(self, arg, argval):
        # https://docs.python.org/3.7/library/dis.html#opcode-CALL_FUNCTION
        #
        # Note: As of Python 3.6 this only supports calls for functions with
        # positional arguments.
        if sys.version_info >= (3, 6):
            argc = arg
            kwargc = 0
        else:
            argc = arg & 0xff
            kwargc = arg >> 8
        kwarg_stack = self._pop_n(2 * kwargc, tos_is_0=False)
        kwargs = dict(zip(kwarg_stack[::2], kwarg_stack[1::2]))
        args = self._pop_n(argc, tos_is_0=False)
        f = self._pop()
        return do_call(f, args, state=self.interpreter_state, kwargs=kwargs,
                       globals_=self.globals_)

    def _run_STORE_NAME(self, arg, argval):
        if self.in_function:
            if self.locals_dict is not None:
                assert isinstance(self.locals_dict, dict)
                # Work around pytype error.
                ld = cast(dict, self.locals_dict)
                ld[argval] = self._pop()
            else:
                self.locals_[arg] = self._pop()
        else:
            v = self._pop()
            self.globals_[argval] = v

    def _run_STORE_ATTR(self, arg, argval):
        obj = self._pop()
        value = self._pop()
        if isinstance(obj, GuestPyObject):
            obj.setattr(argval, value)
        elif obj is sys and argval == 'path':
            sys.path = self.interpreter_state.paths = value
        else:
            raise NotImplementedError(obj, value)

    def _run_STORE_GLOBAL(self, arg, argval):
        self.globals_[argval] = self._pop()

    def _run_MAKE_CLOSURE(self, arg, argval):
        # Note: this bytecode was removed in Python 3.6.
        name = self._pop()
        code = self._pop()
        freevar_cells = self._pop()
        defaults = self._pop_n(arg)
        f = GuestFunction(code, self.globals_, name, defaults=defaults,
                          closure=freevar_cells)
        return Result(f)

    def _run_LOAD_FAST(self, arg, argval):
        v = self.locals_[arg]
        if v is UnboundLocalSentinel:
            msg = 'name {!r} is not defined'.format(argval)
            return Result(ExceptionData(None, None, NameError(msg)))
        return Result(v)

    def _run_IMPORT_NAME(self, arg, argval):
        fromlist = self._pop()
        level = self._pop()
        return import_routines.run_IMPORT_NAME(
            self.code.co_filename, level, fromlist, argval, self.globals_,
            interp, self.interpreter_state)

    def _run_IMPORT_FROM(self, arg, argval):
        module = self._peek()
        if isinstance(module, types.ModuleType):
            return Result(getattr(module, argval))
        elif isinstance(module, GuestModule):
            return import_routines.getattr_or_subimport(
                module, argval, self.interpreter_state, interp)
        else:
            raise NotImplementedError(module)

    def _run_LOAD_GLOBAL(self, arg, argval):
        namei = arg
        name = self.names[namei]
        return Result(self._get_global_or_builtin(name))

    def _run_LOAD_NAME(self, arg, argval):
        if self.in_function:
            if self.locals_dict is not None:
                try:
                    return Result(self.locals_dict[argval])
                except KeyError:
                    pass
            else:
                return Result(self.locals_[arg])
        try:
            return Result(self._get_global_or_builtin(argval))
        except AttributeError:
            msg = 'name {!r} is not defined'.format(argval)
            return Result(ExceptionData(
                None, None, NameError(msg)))

    def _run_LOAD_ATTR(self, arg, argval):
        obj = self._pop()
        for type_, methods in _GUEST_BUILTINS.items():
            if isinstance(obj, type_) and argval in methods:
                return Result(GuestBuiltin(
                    '{}.{}'.format(type_.__name__, argval), bound_self=obj))
        if (isinstance(obj, GuestBuiltin) and obj.name == 'type'
                and argval == '__dict__'):
            return Result(type.__dict__)
        elif isinstance(obj, GuestPyObject):
            return obj.getattr(argval)
        elif obj is sys and argval == 'path':
            return Result(self.interpreter_state.paths)
        elif obj is sys and argval == 'modules':
            return Result(self.interpreter_state.sys_modules)
        else:
            try:
                return Result(getattr(obj, argval))
            except AttributeError as e:
                return Result(ExceptionData(None, None, e))

    def _run_COMPARE_OP(self, arg, argval):
        rhs = self._pop()
        lhs = self._pop()
        if argval == 'exception match':
            return Result(_exception_match(lhs, rhs))
        else:
            return _compare(argval, lhs, rhs)

    def _run_END_FINALLY(self, arg, argval):
        # From the Python docs: "The interpreter recalls whether the
        # exception has to be re-raised, or whether the function returns,
        # and continues with the outer-next block."
        if self.exception_data is None:
            pass
        else:
            raise NotImplementedError(self.handling_exception_data,
                                      self.exception_data)

    def _run_binary(self, opname, arg, argval):
        rhs = self._pop()
        lhs = self._pop()
        return _run_binop(opname, lhs, rhs, self.interp_callback)

    def _run_BINARY_ADD(self, arg, argval):
        return self._run_binary('BINARY_ADD', arg, argval)

    def _run_BINARY_SUBTRACT(self, arg, argval):
        return self._run_binary('BINARY_SUBTRACT', arg, argval)

    def _run_BINARY_SUBSCR(self, arg, argval):
        return self._run_binary('BINARY_SUBSCR', arg, argval)

    def _run_BINARY_MULTIPLY(self, arg, argval):
        return self._run_binary('BINARY_MULTIPLY', arg, argval)

    def _run_BINARY_MODULO(self, arg, argval):
        return self._run_binary('BINARY_MODULO', arg, argval)

    def _run_INPLACE_ADD(self, arg, argval):
        lhs = self._pop()
        rhs = self._pop()
        if {type(lhs), type(rhs)} <= _BUILTIN_VALUE_TYPES | {list}:
            return _run_binop('BINARY_ADD', lhs, rhs, self.interp_callback)
        else:
            raise NotImplementedError(lhs, rhs)

    def _run_LOAD_METHOD(self, arg, argval):
        # Note: New in 3.7.
        #
        # https://docs.python.org/3.7/library/dis.html#opcode-LOAD_METHOD
        obj = self._peek()
        attr_result = self._run_LOAD_ATTR(arg, argval)
        if attr_result.is_exception():
            return attr_result
        self._push(attr_result.get_value())
        if _method_requires_self(obj, attr_result.get_value()):
            self._push(obj)
        else:
            self._push(UnboundLocalSentinel)

    def _run_SETUP_EXCEPT(self, arg, argval):
        self.block_stack.append(BlockInfo(
            BlockKind.SETUP_EXCEPT, arg+self.pc+self.pc_to_bc_width[self.pc],
            len(self.stack)))
        if COLOR_TRACE:
            cprint(' ! pushed except to block stack %r' % self.block_stack,
                   color='magenta')

    def _run_STORE_SUBSCR(self, arg, argval):
        tos = self._pop()
        tos1 = self._pop()
        tos2 = self._pop()
        operator.setitem(tos1, tos, tos2)

    def _run_CALL_FUNCTION_KW(self, arg, argval):
        args = arg
        kwarg_names = self._pop()
        kwarg_values = self._pop_n(len(kwarg_names), tos_is_0=False)
        assert len(kwarg_names) == len(kwarg_values), (
            kwarg_names, kwarg_values)
        kwargs = dict(zip(kwarg_names, kwarg_values))
        rest = args-len(kwargs)
        args = self._pop_n(rest, tos_is_0=False)
        to_call = self._pop()
        return do_call(to_call, args, state=self.interpreter_state,
                       kwargs=kwargs, globals_=self.globals_)

    def _run_SETUP_LOOP(self, arg, argval):
        self.block_stack.append(BlockInfo(
            BlockKind.SETUP_LOOP, arg + self.pc + self.pc_to_bc_width[self.pc],
            len(self.stack)))

    def _run_RAISE_VARARGS(self, arg, argval):
        argc = arg
        traceback, parameter, exception = (None, None, None)
        if argc > 2:
            traceback = self._pop()
        if argc > 1:
            parameter = self._pop()
        if argc > 0:
            exception = self._pop()
        if COLOR_TRACE:
            cprint(' ! exception %r %r %r' % (
                        traceback, parameter, exception),
                   color='magenta')
        return Result(ExceptionData(traceback, parameter, exception))

    def _run_CALL_METHOD(self, arg, argval):
        # Note: new in 3.7.
        #
        # https://docs.python.org/3.7/library/dis.html#opcode-CALL_METHOD
        positional_argc = arg
        args = self._pop_n(positional_argc, tos_is_0=False)
        self_value = self._pop()
        method = self._pop()
        if self_value is not UnboundLocalSentinel:
            args = (self_value,) + args
        return do_call(method, args, globals_=self.globals_,
                       state=self.interpreter_state)

    def _run_CALL_FUNCTION_EX(self, arg, argval):
        if arg & 0x1:
            kwargs = self._pop()
        else:
            kwargs = None
        callargs = self._pop()
        func = self._pop()
        return do_call(func, callargs, kwargs=kwargs, globals_=self.globals_,
                       state=self.interpreter_state)

    def _run_IMPORT_STAR(self, arg, argval):
        module = self._peek()
        import_routines.import_star(module, self.globals_)
        self._pop()  # Docs say 'module is popped after loading all names'.

    def _run_UNPACK_SEQUENCE(self, arg, argval):
        # https://docs.python.org/3.7/library/dis.html#opcode-UNPACK_SEQUENCE
        t = self._pop()  # type: Sequence
        # Want to make sure we have a test that exercises this behavior
        # properly, I expect it leaves the remainder in a tuple when arg is <
        # len.
        assert len(t) == arg
        for e in t[::-1]:
            self._push(e)

    def _run_EXTENDED_ARG(self, arg, argval):
        pass  # The to-instruction decoding step already extended the args?

    def _run_one_bytecode(self):
        global _GLOBAL_BYTECODE_COUNT
        _GLOBAL_BYTECODE_COUNT += 1

        instruction = self.pc_to_instruction[self.pc]
        assert instruction is not None

        if COLOR_TRACE:
            cprint('--- to exec:  %4d: %s @ %s %8d' % (
                    self.pc, instruction, self.code.co_filename,
                    _GLOBAL_BYTECODE_COUNT),
                   color='yellow')
            cprint('stack ({}):'.format(len(self.stack)), color='blue')
            for i, value in enumerate(self.stack):
                cprint(' TOS{}: {} :: {!r}'.format(i, type(value), value),
                       color='blue')

        TRACE_DUMPER.note_instruction(instruction)
        TRACE_DUMPER.note_block_stack([
            bs.to_trace() for bs in self.block_stack])

        if instruction.starts_line is not None:
            self.line = instruction.starts_line

        if instruction.opname in ('RETURN_VALUE', 'YIELD_VALUE'):
            return Result(self._pop())

        f = getattr(self, '_run_{}'.format(instruction.opname))

        stack_depth_before = len(self.stack)
        result = f(arg=instruction.arg, argval=instruction.argval)
        if result is None or type(result) is bool:
            pass
        else:
            assert isinstance(result, Result), (
                'Bytecode must return Result', instruction)
            if result.is_exception():
                self.exception_data = result.get_exception()
                self.exception_data.traceback.append(
                    (self.code.co_filename, self.line))
                if self._handle_exception():
                    return None
                else:
                    if COLOR_TRACE:
                        cprint(' ! returning unhandled exception '
                               '%r from %r' % (result, self.code),
                               color='magenta')
                    return result
            else:
                self._push(result.get_value())

        stack_depth_after = len(self.stack)
        if instruction.opname not in (
                # These opcodes claim a value-stack effect, but we use a
                # different stack for block info.
                'SETUP_EXCEPT', 'POP_EXCEPT', 'SETUP_FINALLY', 'END_FINALLY',
                # This op causes the stack_effect call to error.
                'EXTENDED_ARG',
                # These ops may or may not pop the stack.
                'JUMP_IF_FALSE_OR_POP', 'FOR_ITER',
                ):
            stack_effect = dis.stack_effect(instruction.opcode,
                                            instruction.arg)
            assert stack_depth_after-stack_depth_before == stack_effect, (
                instruction, stack_depth_after, stack_depth_before,
                stack_effect)

        f_sets_pc = getattr(f, '_sets_pc', False)
        if not f_sets_pc or f_sets_pc and not result:
            self.pc += self.pc_to_bc_width[self.pc]

        return None

    def _run_to_return_or_yield(self) -> Result[Any]:
        while True:
            bc_result = self._run_one_bytecode()
            if bc_result is None:
                continue
            return bc_result


def interp(code: types.CodeType,
           *,
           globals_: Dict[Text, Any],
           state: InterpreterState,
           locals_dict: Optional[Dict[Text, Any]] = None,
           args: Optional[Tuple[Any, ...]] = None,
           kwargs: Optional[Dict[Text, Any]] = None,
           defaults: Optional[Tuple[Any, ...]] = None,
           kwarg_defaults: Optional[Dict[Text, Any]] = None,
           closure: Optional[Tuple[GuestCell, ...]] = None,
           in_function: bool = True) -> Result[Any]:
    """Evaluates "code" using "globals_" after initializing locals with "args".

    Returns the result of evaluating the code object.

    Args:
        code: Code object to interpret.
        globals_: Global mapping to use (for global references).
        args: Arguments to populate local variables with (for a function
            invocation).
        defaults: Default arguments to use if the arguments haven't been
            populated via invocation.
        in_function: Whether this code is being interpreted at function scope;
            this controls whether generic "name" references resolve against
            globals (vs function locals).

    Implementation note: this is one giant function for the moment, unclear
    whether performance will be important, but this makes it easy for early
    prototyping.

    TODO(cdleary, 2019-01-20): factor.

    TODO(cdleary, 2019-01-21): Use dis.stack_effect to cross-check stack depth
        change.
    """
    closure = closure or ()

    assert len(code.co_freevars) == len(closure), (
        'Invocation did not satisfy closure requirements.', code,
        code.co_freevars, closure)

    def gprint(*args): cprint(*args, color='green')

    if COLOR_TRACE_FUNC:
        gprint('<bytecode>')
        gprint(dis_to_str(code))
        gprint('</bytecode>')
        gprint(code_to_str(code))
        gprint('interpreting:')
        gprint('  loc:         %s:%d' % (code.co_filename,
                                         code.co_firstlineno))
        gprint('  in_function: %s' % in_function)

    if COLOR_TRACE:
        gprint('  co_name:     %r' % code.co_name)
        gprint('  co_argcount: %d' % code.co_argcount)
        gprint('  co_nlocals:  %d' % code.co_nlocals)
        gprint('  co_cellvars: %r' % (code.co_cellvars,))
        gprint('  co_freevars: %r' % (code.co_freevars,))
        gprint('  co_varnames: %r' % (code.co_varnames,))
        gprint('  co_names:    %r' % (code.co_names,))
        gprint('  closure:     %r' % (closure,))
        cprint_lines_after(code.co_filename, code.co_firstlineno)

    # Set up arguments as a precursor to establishing the locals.
    attrs = CodeAttributes.from_code(code)
    arg_result = resolve_args(
        attrs, args, kwargs, defaults, kwarg_defaults)
    if arg_result.is_exception():
        raise NotImplementedError('Exception while resolving args.',
                                  arg_result.get_exception())

    arg_locals, additional_local_count = arg_result.get_value()

    locals_ = (
        arg_locals +
        [UnboundLocalSentinel] * additional_local_count)  # type: List[Any]
    cellvars = tuple(GuestCell(name) for name in code.co_cellvars) + closure

    # Cellvars that match argument names get populated with the argument value,
    # and it seems as though locals_ for that value is never referenced in the
    # bytecode.
    for i, cellvar_name in enumerate(code.co_cellvars):
        if COLOR_TRACE:
            gprint('populating cellvar name: %s' % cellvar_name)
        try:
            index = code.co_varnames.index(cellvar_name)
        except ValueError:
            continue
        else:
            local_value = locals_[index]
            cellvars[i].set(local_value)

    instructions = tuple(dis.get_instructions(code))
    pc_to_instruction = [None] * (
        instructions[-1].offset+1)  # type: List[Optional[dis.Instruction]]
    pc_to_bc_width = [None] * (
        instructions[-1].offset+1)  # type: List[Optional[int]]
    for i, instruction in enumerate(instructions):
        pc_to_instruction[instruction.offset] = instruction
        if i+1 != len(instructions):
            pc_to_bc_width[instruction.offset] = (
                instructions[i+1].offset-instruction.offset)
    del instructions

    f = StatefulFrame(code, pc_to_instruction, pc_to_bc_width, locals_,
                      locals_dict, globals_, cellvars, state, in_function)
    return f._run_to_return_or_yield()


def _do_call_functools_partial(
        args: Tuple[Any, ...],
        kwargs: Optional[Dict[Text, Any]]) -> Result[Any]:
    """Helper for calling `functools.partial`."""
    if kwargs:
        raise NotImplementedError(kwargs)
    guest_partial = GuestPartial(args[0], args[1:])
    return Result(guest_partial)


def do_call(f, args: Tuple[Any, ...],
            *,
            state: InterpreterState,
            globals_: Dict[Text, Any],
            locals_dict: Optional[Dict[Text, Any]] = None,
            kwargs: Optional[Dict[Text, Any]] = None,
            in_function: bool = True) -> Result[Any]:
    assert in_function
    if COLOR_TRACE:
        cprint('Call; f: %r args: %r kwargs: %r' % (f, args, kwargs),
               color='red')

    def interp_callback(*args, **kwargs):
        return interp(*args, **kwargs, state=state)

    def do_call_callback(*args, **kwargs):
        return do_call(*args, **kwargs, state=state)

    kwargs = kwargs or {}
    if f in (dict, range, print, sorted, str, set, tuple, list, hasattr,
             bytearray) + _BUILTIN_EXCEPTION_TYPES:
        return Result(f(*args, **kwargs))
    if f is globals:
        return Result(globals_)
    elif isinstance(f, (GuestFunction, GuestMethod)):
        return f.invoke(args=args, kwargs=kwargs, locals_dict=locals_dict,
                        interp=interp_callback)
    elif isinstance(f, (types.MethodType, types.FunctionType)):
        # Builtin object method.
        return Result(f(*args, **kwargs))
    # TODO(cdleary, 2019-01-22): Consider using an import hook to avoid
    # the C-extension version of functools from being imported so we
    # don't need to consider it specially.
    elif f is functools.partial:
        return _do_call_functools_partial(args, kwargs)
    elif isinstance(f, GuestPartial):
        return f.invoke(args, interp=interp_callback)
    elif isinstance(f, GuestBuiltin):
        return f.invoke(args, interp=interp_callback, call=do_call_callback)
    elif isinstance(f, GuestClass):
        return f.instantiate(args, do_call=do_call_callback, globals_=globals_)
    else:
        raise NotImplementedError(f, args, kwargs)


def run_function(f: types.FunctionType, *args: Tuple[Any, ...],
                 globals_=None) -> Any:
    """Interprets f in the echo interpreter, returns unwrapped result."""
    state = InterpreterState(script_directory=None)
    globals_ = globals_ or globals()
    result = interp(get_code(f), globals_=globals_, defaults=f.__defaults__,
                    args=args, state=state)
    return result.get_value()


def import_path(path: Text, module_name: Text, fully_qualified_name: Text,
                state: InterpreterState) -> Result[import_routines.ModuleT]:
    if COLOR_TRACE_MOD:
        cprint('Importing; path: %r; fq: %r' % (path, fully_qualified_name),
               color='blue')
    result = import_routines.import_path(
        path, module_name, fully_qualified_name, state, interp)
    if COLOR_TRACE_MOD:
        cprint('Imported; result: %r' % (result), color='blue')
    return result
