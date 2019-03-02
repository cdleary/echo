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

    # Use a sentinel value (this class object) to indicate when
    # UnboundLocalErrors have occurred.
    class UnboundLocalSentinel:
        pass

    locals_ = arg_locals + [UnboundLocalSentinel] * additional_local_count
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

    block_stack = []  # type: List[BlockInfo]
    stack = []
    consts = code.co_consts  # LOAD_CONST indexes into this.
    names = code.co_names  # LOAD_GLOBAL uses these names.

    interp_callback = functools.partial(interp, state=state)

    do_call_callback = functools.partial(do_call, state=state)

    # TODO(cdleary, 2019-01-21): Investigate why this "builtins" ref is
    # sometimes a dict and other times a module?
    builtins = sys.modules['builtins']  # globals_['__builtins__']

    def push(x):
        if COLOR_TRACE_STACK:
            cprint(' =(push)=> %r [depth after: %d]' %
                   (x, len(stack)+1), color='blue')
        assert not isinstance(x, Result), x
        # If the user can observe the real isinstance they can break the
        # virtualization abstraction, which is undesirable.
        assert x is not isinstance
        stack.append(x)

    def pop():
        x = stack.pop()
        if COLOR_TRACE_STACK:
            cprint(' <=(pop)= %r [depth after: %d]' %
                   (x, len(stack)), color='blue')
        return x

    def pop_n(n: int, tos_is_0: bool = True) -> Tuple[Any, ...]:
        nonlocal stack
        stack, result = stack[:len(stack)-n], stack[len(stack)-n:]
        if tos_is_0:
            return tuple(reversed(result))
        return tuple(result)

    def peek(): return stack[-1]

    def get_global_or_builtin(name):
        try:
            return globals_[name]
        except KeyError:
            pass
        return builtins_get(builtins, name)

    def handle_exception():
        """Returns whether the exception was handled in this function."""
        nonlocal pc, exception_data, handling_exception_data
        if COLOR_TRACE:
            cprint(' ! handling exception with block stack %r; %r' % (
                    block_stack, exception_data), color='magenta')
        while block_stack and block_stack[-1].kind != BlockKind.SETUP_EXCEPT:
            block_stack.pop()
        if block_stack and block_stack[-1].kind == BlockKind.SETUP_EXCEPT:
            pc = block_stack[-1].handler
            if COLOR_TRACE:
                cprint(' ! moved PC to %d' % pc, color='magenta')
            while len(stack) > block_stack[-1].level:
                pop()
            assert isinstance(exception_data, ExceptionData)
            push(exception_data.traceback)
            push(exception_data.exception)
            push(exception_data.exception)
            block_stack[-1].kind = BlockKind.EXCEPT_HANDLER
            block_stack[-1].handler = -1
            handling_exception_data, exception_data = exception_data, None
            return True
        elif not any(entry.kind == BlockKind.SETUP_EXCEPT
                     for entry in block_stack):
            return False  # Definitely unhandled.
        else:
            # Need to pop block stack entries appropriately, then handle the
            # exception.
            raise NotImplementedError(block_stack)

    instructions = tuple(dis.get_instructions(code))
    pc_to_instruction = [None] * (
        instructions[-1].offset+1)  # type: List[Optional[dis.Instruction]]
    pc_to_bc_width = [None] * (
        instructions[-1].offset+1)  # type: List[Optional[int]]
    exception_data = None  # type: Optional[ExceptionData]
    handling_exception_data = None  # type: Optional[ExceptionData]
    for i, instruction in enumerate(instructions):
        pc_to_instruction[instruction.offset] = instruction
        if i+1 != len(instructions):
            pc_to_bc_width[instruction.offset] = (
                instructions[i+1].offset-instruction.offset)
    del instructions

    pc = 0

    DISPATCH_TABLE = {}

    def dispatched(f):
        f_name = f.__name__
        assert f_name.startswith('run_')
        opname = f_name[len('run_'):]
        assert opname not in DISPATCH_TABLE, opname
        DISPATCH_TABLE[opname] = f
        return f

    @dispatched
    def run_SETUP_LOOP(arg, argval):
        block_stack.append(BlockInfo(
            BlockKind.SETUP_LOOP, arg + pc + pc_to_bc_width[pc], len(stack)))

    @dispatched
    def run_SETUP_EXCEPT(arg, argval):
        block_stack.append(BlockInfo(
            BlockKind.SETUP_EXCEPT, arg+pc+pc_to_bc_width[pc], len(stack)))
        if COLOR_TRACE:
            cprint(' ! pushed except to block stack %r' % block_stack,
                   color='magenta')

    @dispatched
    def run_SETUP_FINALLY(arg, argval):
        # "Pushes a try block from a try-except clause onto the block stack.
        # delta points to the finally block."
        # -- https://docs.python.org/3.7/library/dis.html#opcode-SETUP_FINALLY
        block_stack.append(BlockInfo(
            BlockKind.SETUP_FINALLY, arg+pc+pc_to_bc_width[pc], len(stack)))

    @dispatched
    def run_EXTENDED_ARG(arg, argval):
        pass  # The to-instruction decoding step already extended the args?

    @dispatched
    def run_POP_EXCEPT(arg, argval):
        if COLOR_TRACE:
            cprint(' ! popping except with block stack %r' % block_stack,
                   color='magenta')
        popped = block_stack.pop()
        assert popped.kind in (BlockKind.SETUP_EXCEPT,
                               BlockKind.EXCEPT_HANDLER), (
            'Popped non-except block.', popped)

    @dispatched
    def run_RAISE_VARARGS(arg, argval):
        argc = arg
        traceback, parameter, exception = (None, None, None)
        if argc > 2:
            traceback = pop()
        if argc > 1:
            parameter = pop()
        if argc > 0:
            exception = pop()
        if COLOR_TRACE:
            cprint(' ! exception %r %r %r' % (
                        traceback, parameter, exception),
                   color='magenta')
        return Result(ExceptionData(traceback, parameter, exception))

    @dispatched
    def run_LOAD_GLOBAL(arg, argval):
        namei = arg
        name = names[namei]
        return Result(get_global_or_builtin(name))

    @dispatched
    def run_LOAD_CONST(arg, argval):
        return Result(consts[arg])

    @dispatched
    def run_STORE_FAST(arg, argval):
        locals_[arg] = pop()

    @dispatched
    def run_IMPORT_NAME(arg, argval):
        fromlist = pop()
        level = pop()
        return import_routines.run_IMPORT_NAME(
            code.co_filename, level, fromlist, argval, globals_, interp, state)

    @dispatched
    def run_IMPORT_STAR(arg, argval):
        module = peek()
        import_routines.import_star(module, globals_)
        pop()  # Docs say 'module is popped after loading all names'.

    @dispatched
    def run_IMPORT_FROM(arg, argval):
        module = peek()
        if isinstance(module, types.ModuleType):
            return Result(getattr(module, argval))
        elif isinstance(module, GuestModule):
            return import_routines.getattr_or_subimport(module, argval, state,
                                                        interp)
        else:
            raise NotImplementedError(module)

    @dispatched
    def run_LOAD_ATTR(arg, argval):
        obj = pop()
        for type_, methods in _GUEST_BUILTINS.items():
            if isinstance(obj, type_) and argval in methods:
                return Result(GuestBuiltin(
                    '{}.{}'.format(type_.__name__, argval), bound_self=obj))
        if isinstance(obj, GuestPyObject):
            return obj.getattr(argval)
        elif obj is sys and argval == 'path':
            return Result(state.paths)
        elif obj is sys and argval == 'modules':
            return Result(state.sys_modules)
        else:
            try:
                return Result(getattr(obj, argval))
            except AttributeError as e:
                return Result(ExceptionData(None, None, e))

    @dispatched
    def run_LOAD_METHOD(arg, argval):
        # Note: New in 3.7.
        #
        # https://docs.python.org/3.7/library/dis.html#opcode-LOAD_METHOD
        obj = peek()
        attr_result = run_LOAD_ATTR(arg, argval)
        if attr_result.is_exception():
            return attr_result
        push(attr_result.get_value())
        if _method_requires_self(obj, attr_result.get_value()):
            push(obj)
        else:
            push(UnboundLocalSentinel)

    @dispatched
    def run_STORE_ATTR(arg, argval):
        obj = pop()
        value = pop()
        if isinstance(obj, GuestPyObject):
            obj.setattr(argval, value)
        elif obj is sys and argval == 'path':
            sys.path = state.paths = value
        else:
            raise NotImplementedError(obj, value)

    @dispatched
    def run_COMPARE_OP(arg, argval):
        rhs = pop()
        lhs = pop()
        if argval == 'exception match':
            return Result(_exception_match(lhs, rhs))
        else:
            return _compare(argval, lhs, rhs)

    @dispatched
    def run_CALL_METHOD(arg, argval):
        # Note: new in 3.7.
        #
        # https://docs.python.org/3.7/library/dis.html#opcode-CALL_METHOD
        positional_argc = arg
        args = pop_n(positional_argc, tos_is_0=False)
        self_value = pop()
        method = pop()
        if self_value is not UnboundLocalSentinel:
            args = (self_value,) + args
        return do_call(method, args, globals_=globals_, state=state)

    @dispatched
    def run_CALL_FUNCTION_KW(arg, argval):
        args = arg
        kwarg_names = pop()
        kwarg_values = pop_n(len(kwarg_names), tos_is_0=False)
        assert len(kwarg_names) == len(kwarg_values), (
            kwarg_names, kwarg_values)
        kwargs = dict(zip(kwarg_names, kwarg_values))
        rest = args-len(kwargs)
        args = pop_n(rest, tos_is_0=False)
        to_call = pop()
        return do_call(to_call, args, state=state, kwargs=kwargs,
                       globals_=globals_)

    @dispatched
    def run_CALL_FUNCTION_EX(arg, argval):
        if arg & 0x1:
            kwargs = pop()
        else:
            kwargs = None
        callargs = pop()
        func = pop()
        return do_call(func, callargs, kwargs=kwargs, globals_=globals_,
                       state=state)

    @dispatched
    def run_CALL_FUNCTION(arg, argval):
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
        kwarg_stack = pop_n(2 * kwargc, tos_is_0=False)
        kwargs = dict(zip(kwarg_stack[::2], kwarg_stack[1::2]))
        args = pop_n(argc, tos_is_0=False)
        f = pop()
        return do_call(f, args, state=state, kwargs=kwargs,
                       globals_=globals_)

    @dispatched
    def run_INPLACE_ADD(arg, argval):
        lhs = pop()
        rhs = pop()
        if {type(lhs), type(rhs)} <= _BUILTIN_VALUE_TYPES | {list}:
            return _run_binop('BINARY_ADD', lhs, rhs, interp_callback)
        else:
            raise NotImplementedError(lhs, rhs)

    @dispatched
    def run_STORE_SUBSCR(arg, argval):
        tos = pop()
        tos1 = pop()
        tos2 = pop()
        operator.setitem(tos1, tos, tos2)

    @dispatched
    def run_MAKE_CLOSURE(arg, argval):
        # Note: this bytecode was removed in Python 3.6.
        name = pop()
        code = pop()
        freevar_cells = pop()
        defaults = pop_n(arg)
        f = GuestFunction(code, globals_, name, defaults=defaults,
                          closure=freevar_cells)
        return Result(f)

    @dispatched
    def run_STORE_GLOBAL(arg, argval):
        globals_[argval] = pop()

    @dispatched
    def run_STORE_NAME(arg, argval):
        if in_function:
            if locals_dict is not None:
                assert isinstance(locals_dict, dict)
                # Work around pytype error.
                ld = cast(dict, locals_dict)
                ld[argval] = pop()
            else:
                locals_[arg] = pop()
        else:
            v = pop()
            globals_[argval] = v

    @dispatched
    def run_LOAD_NAME(arg, argval):
        if in_function:
            if locals_dict is not None:
                try:
                    return Result(locals_dict[argval])
                except KeyError:
                    pass
            else:
                return Result(locals_[arg])
        try:
            return Result(get_global_or_builtin(argval))
        except AttributeError:
            msg = 'name {!r} is not defined'.format(argval)
            return Result(ExceptionData(
                None, None, NameError(msg)))

    @dispatched
    def run_LOAD_FAST(arg, argval):
        v = locals_[arg]
        if v is UnboundLocalSentinel:
            msg = 'name {!r} is not defined'.format(argval)
            return Result(ExceptionData(None, None, NameError(msg)))
        return Result(v)

    @dispatched
    def run_DELETE_NAME(arg, argval):
        if in_function:
            locals_[arg] = UnboundLocalSentinel
        else:
            del globals_[argval]

    @dispatched
    def run_DELETE_SUBSCR(arg, argval):
        tos = pop()
        tos1 = pop()
        if isinstance(tos1, dict):
            del tos1[tos]
        elif isinstance(tos1, GuestPyObject):
            tos1.delattr(tos)
        else:
            raise NotImplementedError(tos, tos1)

    @dispatched
    def run_POP_TOP(arg, argval):
        pop()

    @dispatched
    def run_LIST_APPEND(arg, argval):
        tos = pop()
        tos_mi = stack[-arg]
        list.append(tos_mi, tos)

    @dispatched
    def run_POP_BLOCK(arg, argval):
        block_stack.pop()

    @dispatched
    def run_MAKE_FUNCTION(arg, argval):
        if sys.version_info >= (3, 6):
            qualified_name = pop()
            code = pop()
            freevar_cells = pop() if arg & 0x08 else None
            annotation_dict = pop() if arg & 0x04 else None
            kwarg_defaults = pop() if arg & 0x02 else None
            positional_defaults = pop() if arg & 0x01 else None
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
            qualified_name = pop()
            code = pop()
            kwarg_default_items = pop_n(2 * name_and_default_pairs,
                                        tos_is_0=False)
            kwarg_defaults = dict(zip(kwarg_default_items[::2],
                                      kwarg_default_items[1::2]))
            positional_defaults = pop_n(default_argc, tos_is_0=False)
            freevar_cells = None

        f = GuestFunction(code, globals_, qualified_name,
                          defaults=positional_defaults,
                          kwarg_defaults=kwarg_defaults, closure=freevar_cells)
        return Result(f)

    @dispatched
    def run_UNPACK_SEQUENCE(arg, argval):
        # https://docs.python.org/3.7/library/dis.html#opcode-UNPACK_SEQUENCE
        t = pop()
        # Want to make sure we have a test that exercises this behavior
        # properly, I expect it leaves the remainder in a tuple when arg is <
        # len.
        assert len(t) == arg
        for e in t[::-1]:
            push(e)

    line = None
    while True:
        instruction = pc_to_instruction[pc]
        if instruction.starts_line is not None:
            line = instruction.starts_line
        TRACE_DUMPER.note_instruction(instruction)
        TRACE_DUMPER.note_block_stack([bs.to_trace() for bs in block_stack])
        assert instruction is not None
        global _GLOBAL_BYTECODE_COUNT
        _GLOBAL_BYTECODE_COUNT += 1
        if COLOR_TRACE:
            cprint('--- to exec:  %4d: %s @ %s %8d' % (
                    pc, instruction, code.co_filename, _GLOBAL_BYTECODE_COUNT),
                   color='yellow')
            cprint('stack ({}):'.format(len(stack)), color='blue')
            for i, value in enumerate(stack):
                cprint(' TOS{}: {} :: {!r}'.format(i, type(value), value),
                       color='blue')
        opname = instruction.opname
        f = DISPATCH_TABLE.get(opname)
        if f:
            stack_depth_before = len(stack)
            result = f(arg=instruction.arg, argval=instruction.argval)
            if result is None:
                pass
            else:
                assert isinstance(result, Result), (
                    'Bytecode must return Result', instruction)
                if result.is_exception():
                    exception_data = result.get_exception()
                    exception_data.traceback.append((code.co_filename, line))
                    if handle_exception():
                        continue
                    else:
                        if COLOR_TRACE:
                            cprint(' ! returning unhandled exception '
                                   '%r from %r' % (result, code),
                                   color='magenta')
                        return result
                else:
                    push(result.get_value())
            stack_depth_after = len(stack)
            if instruction.opname not in (
                    # These opcodes claim a value-stack effect, but we use a
                    # different stack for block info.
                    'SETUP_EXCEPT', 'POP_EXCEPT', 'SETUP_FINALLY',
                    # This op causes the stack_effect call to error.
                    'EXTENDED_ARG'):
                stack_effect = dis.stack_effect(instruction.opcode,
                                                instruction.arg)
                assert stack_depth_after-stack_depth_before == stack_effect, (
                    instruction, stack_depth_after, stack_depth_before,
                    stack_effect)
        elif opname == 'END_FINALLY':
            # From the Python docs: "The interpreter recalls whether the
            # exception has to be re-raised, or whether the function returns,
            # and continues with the outer-next block."
            if exception_data is None:
                pass
            else:
                raise NotImplementedError(handling_exception_data,
                                          exception_data)
        elif opname == 'CALL_FUNCTION_VAR':
            raise NotImplementedError
        elif opname == 'GET_ITER':
            push(pop().__iter__())
        elif opname == 'FOR_ITER':
            try:
                push(peek().__next__())
            except StopIteration:
                pop()
                pc += pc_to_bc_width[pc] + instruction.arg
                new_instruction = pc_to_instruction[pc]
                assert new_instruction is not None
                assert new_instruction.is_jump_target, (
                    'Attempted to jump to invalid target.', pc,
                    pc_to_instruction[pc])
                continue
        elif opname == 'LOAD_BUILD_CLASS':
            push(GuestBuiltin('__build_class__', None))
        elif opname == 'BREAK_LOOP':
            loop_block = block_stack[-1]
            assert loop_block.kind == BlockKind.SETUP_LOOP
            pc = loop_block.handler
            continue
        elif opname == 'JUMP_ABSOLUTE':
            pc = instruction.arg
            continue
        elif opname == 'JUMP_FORWARD':
            pc += instruction.arg + pc_to_bc_width[pc]
            continue
        elif opname == 'POP_JUMP_IF_FALSE':
            if is_false(pop()):
                pc = instruction.arg
                continue
        elif opname == 'POP_JUMP_IF_TRUE':
            if is_true(pop()):
                pc = instruction.arg
                continue
        elif opname == 'JUMP_IF_FALSE_OR_POP':
            if is_false(peek()):
                pc = instruction.arg
                continue
            else:
                pop()
        elif opname == 'RETURN_VALUE':
            return Result(pop())
        elif opname == 'BUILD_TUPLE':
            count = instruction.arg
            t = pop_n(count, tos_is_0=False)
            push(t)
        elif opname == 'BUILD_MAP':
            items = pop_n(2 * instruction.arg, tos_is_0=False)
            ks = items[::2]
            vs = items[1::2]
            push(dict(zip(ks, vs)))
        elif opname == 'BUILD_CONST_KEY_MAP':
            count = instruction.arg
            ks = pop()
            stack, vs = stack[:-count], tuple(stack[-count:])
            assert len(ks) == len(vs)
            push(dict(zip(ks, vs)))
        elif opname == 'BUILD_TUPLE_UNPACK':
            iterables = pop_n(instruction.arg, tos_is_0=False)
            push(tuple(itertools.chain(*iterables)))
        elif opname == 'BUILD_LIST':
            count = instruction.arg
            limit = len(stack)-count
            stack, t = stack[:limit], stack[limit:]
            push(t)
        elif opname == 'BUILD_SET':
            count = instruction.arg
            limit = len(stack)-count
            stack, t = stack[:limit], stack[limit:]
            push(set(t))
        elif opname.startswith('BINARY'):
            # Probably need to handle radd and such here.
            rhs = pop()
            lhs = pop()
            result = _run_binop(opname, lhs, rhs, interp_callback)
            if result.is_exception():
                raise NotImplementedError
            else:
                push(result.get_value())
        elif opname == 'LOAD_DEREF':
            push(cellvars[instruction.arg].get())
        elif opname == 'STORE_DEREF':
            cellvars[instruction.arg].set(pop())
        elif opname == 'LOAD_CLOSURE':
            cellvar = cellvars[instruction.arg]
            push(cellvar)
        elif opname == 'DUP_TOP_TWO':
            stack = stack + stack[-2:]
        elif opname == 'DUP_TOP':
            assert stack, 'Cannot DUP_TOP of empty stack.'
            stack = stack + stack[-1:]
        elif opname == 'ROT_TWO':
            stack[-1], stack[-2] = stack[-2], stack[-1]
        elif opname == 'ROT_THREE':
            #                                  old first  old second  old third
            stack[-3], stack[-1], stack[-2] = stack[-1], stack[-2], stack[-3]
        else:
            raise NotImplementedError(instruction, stack)
        pc += pc_to_bc_width[pc]


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
