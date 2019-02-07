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
                    Iterable)

from termcolor import cprint

from common import dis_to_str, get_code
from interp_result import Result, ExceptionData
import import_routines
from interpreter_state import InterpreterState
from guest_objects import (GuestModule, GuestFunction, GuestInstance,
                           GuestBuiltin, GuestPyObject, GuestPartial,
                           GuestClass)


_GLOBAL_BYTECODE_COUNT = 0
COLOR_TRACE_FUNC = False
COLOR_TRACE_STACK = False
COLOR_TRACE_MOD = False
COLOR_TRACE = False
STARARGS_FLAG = 0x04
_BINARY_OPS = {
    'BINARY_ADD': operator.add,
    'BINARY_MODULO': operator.mod,
    'BINARY_MULTIPLY': operator.mul,
    'BINARY_SUBSCR': operator.getitem,
    'BINARY_TRUE_DIVIDE': operator.truediv,
}
_BUILTIN_TYPES = {
    int,
    str,
    list,
}
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
    '>=': operator.ge,
    'is not': operator.is_not,
}


def is_false(v: Any) -> bool:
    if isinstance(v, int):
        return v == 0
    if isinstance(v, bool):
        return v is False
    else:
        raise NotImplementedError(v)


def is_true(v: Any) -> bool:
    return not is_false(v)


def code_to_str(c: types.CodeType) -> Text:
    guts = ', '.join('{}={!r}'.format(attr.split('_')[1], getattr(c, attr))
                     for attr in _CODE_ATTRS)
    return 'Code({})'.format(guts)


def builtins_get(builtins: Union[types.ModuleType, Dict], name: Text) -> Any:
    if isinstance(builtins, types.ModuleType):
        return getattr(builtins, name)
    return builtins[name]


class GuestCell:
    def __init__(self, name: Text):
        self._name = name
        self._storage = GuestCell

    def initialized(self) -> bool:
        return self._storage is not GuestCell

    def get(self) -> Any:
        assert self._storage is not GuestCell, (
            'GuestCell %r is uninitialized' % self._name)
        return self._storage

    def set(self, value: Any):
        self._storage = value


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


def _run_binop(opname: Text, lhs: Any, rhs: Any) -> Result[Any]:
    if (opname in ('BINARY_TRUE_DIVIDE', 'BINARY_MODULO') and type(rhs) is int
            and rhs == 0):
        raise NotImplementedError(opname, lhs, rhs)
    if {type(lhs), type(rhs)} <= _BUILTIN_TYPES:
        op = _BINARY_OPS[opname]
        return Result(op(lhs, rhs))
    raise NotImplementedError(opname, lhs, rhs)


def _exception_match(lhs, rhs) -> bool:
    if isinstance(lhs, rhs):
        return True
    if lhs is rhs:
        return True
    raise NotImplementedError(lhs, rhs)


def module_getattr(module: Union[types.ModuleType, GuestModule],
                   name: Text) -> Any:
    if isinstance(module, GuestModule):
        return module.getattr(name)
    return getattr(module, name)


def interp(code: types.CodeType,
           *,
           globals_: Dict[Text, Any],
           state: InterpreterState,
           args: Optional[Tuple[Any, ...]] = None,
           kwargs: Optional[Dict[Text, Any]] = None,
           defaults: Optional[Tuple[Any, ...]] = None,
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
    if kwargs:
        raise NotImplementedError(code, kwargs)
    args = args or ()
    defaults = defaults or ()
    closure = closure or ()

    assert len(code.co_freevars) == len(closure), (
        'Invocation did not satisfy closure requirements.', code,
        code.co_freevars, closure)

    logging.debug('<bytecode>')
    logging.debug(dis_to_str(code))
    logging.debug('</bytecode>')
    logging.debug(code_to_str(code))

    # Note: co_argcount includes default arguments in the count.
    assert (len(args) + len(defaults) >= code.co_argcount
            or code.co_flags & STARARGS_FLAG), (
        'Invocation did not provide enough arguments.', code, args, defaults,
        code.co_argcount)

    locals_ = (list(args) + list(defaults)
               + [None] * (code.co_nlocals-code.co_argcount))
    cellvars = tuple(GuestCell(name) for name in code.co_cellvars) + closure

    # Cellvars that match argument names get populated with the argument value,
    # and it seems as though locals_ for that value is never referenced in the
    # bytecode.
    for i, cellvar_name in enumerate(code.co_cellvars):
        try:
            index = code.co_cellvars.index(cellvar_name)
        except ValueError:
            continue
        else:
            cellvars[i].set(locals_[index])

    block_stack = []
    stack = []
    consts = code.co_consts  # LOAD_CONST indexes into this.
    names = code.co_names  # LOAD_GLOBAL uses these names.

    interp_callback = functools.partial(interp, state=state)

    def gprint(*args): cprint(*args, color='green')

    if COLOR_TRACE_FUNC:
        gprint('interpreting:')
        gprint('  loc:         %s:%d' % (code.co_filename,
                                         code.co_firstlineno))
    if COLOR_TRACE:
        gprint('  co_name:     %r' % code.co_name)
        gprint('  co_argcount: %d' % code.co_argcount)
        gprint('  co_nlocals:  %d' % code.co_nlocals)
        gprint('  co_cellvars: %r' % (code.co_cellvars,))
        gprint('  co_freevars: %r' % (code.co_freevars,))
        gprint('  co_varnames: %r' % (code.co_varnames,))
        gprint('  co_names:    %r' % (code.co_names,))
        gprint('  closure:     %r' % (closure,))
        gprint('  len(args):   %d' % len(args))
        cprint_lines_after(code.co_filename, code.co_firstlineno)

    # TODO(cdleary, 2019-01-21): Investigate why this "builtins" ref is
    # sometimes a dict and other times a module?
    builtins = globals_['__builtins__']

    def push(x):
        if COLOR_TRACE_STACK:
            cprint(' =(push)=> %r [depth after: %d]' %
                   (x, len(stack)+1), color='blue')
        assert not isinstance(x, Result), x
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
            return builtins_get(builtins, name)

    def handle_exception():
        """Returns whether the exception was handled in this function."""
        nonlocal pc
        if block_stack and block_stack[-1][0] == 'except':
            pc = block_stack[-1][1]
            if COLOR_TRACE:
                cprint(' ! moved PC to %d' % pc, color='magenta')
            push(exception_data.traceback)
            push(exception_data.parameter)
            push(exception_data.exception)
            return True
        elif not any(entry[0] == 'except' for entry in block_stack):
            return False  # Definitely unhandled.
        else:
            # Need to pop block stack entries appropriately, then handle the
            # exception.
            raise NotImplementedError

    def import_star(module):
        for name in module.keys():
            if COLOR_TRACE_FUNC:
                cprint('IMPORT_STAR module key: %r' % name, color='green')
            if not name.startswith('_'):
                globals_[name] = module.getattr(name)

    instructions = tuple(dis.get_instructions(code))
    pc_to_instruction = [None] * (
        instructions[-1].offset+1)  # type: List[Optional[dis.Instruction]]
    pc_to_bc_width = [None] * (
        instructions[-1].offset+1)  # type: List[Optional[int]]
    exception_data = None  # type: Optional[ExceptionData]
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
        DISPATCH_TABLE[opname] = f
        return f

    @dispatched
    def run_SETUP_LOOP(arg, argval):
        block_stack.append(('loop',
                            arg + pc + pc_to_bc_width[pc]))

    @dispatched
    def run_SETUP_EXCEPT(arg, argval):
        block_stack.append(('except',
                            arg+pc+pc_to_bc_width[pc]))

    @dispatched
    def run_EXTENDED_ARG(arg, argval):
        pass  # The to-instruction decoding step already extended the args?

    @dispatched
    def run_POP_EXCEPT(arg, argval):
        popped = block_stack.pop()
        assert popped[0] == 'except', 'Popped non-except block.'

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
        if COLOR_TRACE_FUNC:
            cprint('IMPORT_NAME argval: %r; fromlist: %r; level: %r' %
                   (argval, fromlist, level), color='green')
        more_paths = import_routines.resolve_level_to_dirpaths(
            code.co_filename, level)
        result = import_routines.do_import(
            argval, globals_=globals_, interp=interp_callback, state=state,
            more_paths=more_paths)
        if COLOR_TRACE:
            cprint('IMPORT_NAME result: %r' % result, color='blue')
        if result.is_exception():
            return result
        # Not an exception.
        module = result.get_value()
        for name in fromlist or ():
            if name == '*':
                import_star(module)
            else:
                try:
                    globals_[name] = module_getattr(module, name)
                except KeyError:
                    # "Note that when using from package import item, the item
                    # can be either a submodule (or subpackage) of the package,
                    # or some other name defined in the package, like a
                    # function, class or variable. The import statement first
                    # tests whether the item is defined in the package; if not,
                    # it assumes it is a module and attempts to load it. If it
                    # fails to find it, an ImportError exception is raised."
                    # -- https://docs.python.org/3/tutorial/modules.html
                    result = import_routines.do_subimport(
                        module, name, interp=interp_callback, state=state,
                        globals_=globals_)
                    if result.is_exception():
                        return result
                    module = result.get_value()

        if COLOR_TRACE:
            cprint('IMPORT_NAME result: %r' % module, color='green')
        return Result(module)

    @dispatched
    def run_IMPORT_STAR(arg, argval):
        module = peek()
        import_star(module)
        pop()  # Docs say 'module is popped after loading all names'.

    @dispatched
    def run_IMPORT_FROM(arg, argval):
        module = peek()
        if isinstance(module, types.ModuleType):
            return Result(getattr(module, argval))
        elif isinstance(module, GuestModule):
            try:
                return Result(module.getattr(argval))
            except KeyError:
                return import_routines.do_subimport(
                    module, argval, interp=interp_callback, state=state,
                    globals_=globals_)
        else:
            raise NotImplementedError(module)

    @dispatched
    def run_LOAD_ATTR(arg, argval):
        obj = pop()
        logging.debug('obj: %r; argval: %r', obj, argval)
        if isinstance(obj, dict) and argval == 'keys':
            return Result(GuestBuiltin('dict.keys', bound_self=obj))
        elif isinstance(obj, GuestPyObject):
            return Result(obj.getattr(argval))
        else:
            return Result(getattr(obj, argval))

    @dispatched
    def run_STORE_ATTR(arg, argval):
        obj = pop()
        value = pop()
        if isinstance(obj, GuestPyObject):
            obj.setattr(argval, value)
        else:
            raise NotImplementedError

    @dispatched
    def run_COMPARE_OP(arg, argval):
        rhs = pop()
        lhs = pop()
        if argval in ('in', 'not in'):
            op = ((lambda x, y: operator.contains(x, y))
                  if argval == 'in'
                  else lambda x, y: not operator.contains(x, y))
            if type(rhs) in (list, dict, set):
                return Result(op(rhs, lhs))
            else:
                raise NotImplementedError(lhs, rhs)
        elif argval == 'exception match':
            return Result(_exception_match(lhs, rhs))
        else:
            op = _COMPARE_OPS[argval]
            types_ = {type(lhs), type(rhs)}
            if types_ <= _BUILTIN_TYPES:
                push(op(lhs, rhs))
            elif (isinstance(lhs, GuestInstance) and
                  isinstance(rhs, GuestInstance) and
                  argval in ('is not', 'is')):
                return Result(op(lhs, rhs))
            else:
                raise NotImplementedError(lhs, rhs)

    @dispatched
    def run_CALL_FUNCTION_KW(arg, argval):
        args = arg
        kwarg_names = pop()
        kwarg_values = pop_n(len(kwarg_names), tos_is_0=True)
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
        # As of Python 3.6 this only supports calls for functions with
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
        if {type(lhs), type(rhs)} <= _BUILTIN_TYPES:
            return _run_binop('BINARY_ADD', lhs, rhs)
        else:
            raise NotImplementedError(lhs, rhs)

    @dispatched
    def run_MAKE_FUNCTION(arg, argval):
        qualified_name = pop()
        code = pop()
        closure = None
        defaults = None
        if arg & 0x08:
            assert isinstance(peek(), tuple), peek()
            closure = pop()
        if arg & 0x04:
            raise NotImplementedError
        if arg & 0x02:
            raise NotImplementedError
        if arg & 0x01:
            defaults = pop()
        f = GuestFunction(code, globals_, qualified_name,
                          defaults=defaults, closure=closure)
        return Result(f)

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
    def run_STORE_NAME(arg, argval):
        if in_function:
            locals_[arg] = pop()
        else:
            globals_[argval] = pop()

    @dispatched
    def run_POP_TOP(arg, argval):
        pop()

    @dispatched
    def run_POP_BLOCK(arg, argval):
        block_stack.pop()

    @dispatched
    def run_MAKE_FUNCTION(arg, argval):
        qualified_name = pop()
        code = pop()
        freevar_cells = pop() if arg & 0x08 else None
        annotation_dict = pop() if arg & 0x04 else None
        kwarg_defaults = pop() if arg & 0x02 else None
        positional_defaults = pop() if arg & 0x01 else None
        if kwarg_defaults:
            raise NotImplementedError(kwarg_defaults)
        if annotation_dict:
            raise NotImplementedError(annotation_dict)
        f = GuestFunction(code, globals_, qualified_name,
                          defaults=positional_defaults, closure=freevar_cells)
        return Result(f)

    while True:
        instruction = pc_to_instruction[pc]
        assert instruction is not None
        global _GLOBAL_BYTECODE_COUNT
        _GLOBAL_BYTECODE_COUNT += 1
        if COLOR_TRACE:
            cprint('%4d: %s @ %s %8d' % (pc, instruction, code.co_filename,
                   _GLOBAL_BYTECODE_COUNT),
                   color='yellow')
        opname = instruction.opname
        f = DISPATCH_TABLE.get(opname)
        if f:
            result = f(arg=instruction.arg, argval=instruction.argval)
            if result is None:
                pass
            else:
                assert isinstance(result, Result)
                if result.is_exception():
                    exception_data = result.get_exception()
                    if handle_exception():
                        continue
                    else:
                        return result
                else:
                    push(result.get_value())
        elif opname == 'END_FINALLY':
            # From the Python docs: "The interpreter recalls whether the
            # exception has to be re-raised, or whether the function returns,
            # and continues with the outer-next block."
            raise NotImplementedError
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
                assert pc_to_instruction[pc].is_jump_target, (
                    'Attempted to jump to invalid target.', pc,
                    pc_to_instruction[pc])
                continue
        elif opname == 'LOAD_FAST':
            push(locals_[instruction.arg])
        elif opname == 'LOAD_BUILD_CLASS':
            push(builtins_get(builtins, '__build_class__'))
        elif opname == 'BREAK_LOOP':
            loop_block = block_stack[-1]
            assert loop_block[0] == 'loop'
            pc = loop_block[1]
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
            stack, t = stack[:-count], tuple(stack[-count:])
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
            stack, t = stack[:-count], stack[-count:]
            push(t)
        elif opname.startswith('BINARY'):
            # Probably need to handle radd and such here.
            rhs = pop()
            lhs = pop()
            result = _run_binop(opname, lhs, rhs)
            if result.is_exception():
                raise NotImplementedError
            else:
                push(result.get_value())
        elif opname == 'LOAD_NAME':
            if in_function:
                raise NotImplementedError
            else:
                push(get_global_or_builtin(instruction.argval))
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
            kwargs: Optional[Dict[Text, Any]] = None) -> Result[Any]:
    interp_callback = functools.partial(interp, state=state)
    do_call_callback = functools.partial(do_call, state=state)
    kwargs = kwargs or {}
    if f in (dict, range, print, sorted, str, list, ValueError,
             AssertionError):
        return Result(f(*args, **kwargs))
    if f is globals:
        return Result(globals_)
    elif isinstance(f, GuestFunction):
        return interp(f.code, state=state, globals_=f.globals_, args=args,
                      kwargs=kwargs, closure=f.closure)
    elif isinstance(f, types.FunctionType):
        return interp(f.__code__, state=state, globals_=f.__globals__,
                      defaults=f.__defaults__, args=args, kwargs=kwargs)
    elif isinstance(f, types.MethodType):
        # Builtin object method.
        return Result(f(*args, **kwargs))
    # TODO(cdleary, 2019-01-22): Consider using an import hook to avoid
    # the C-extension version of functools from being imported so we
    # don't need to consider it specially.
    elif f is functools.partial:
        return _do_call_functools_partial(args, kwargs)
    elif f is getattr(builtins, '__build_class__'):
        body_f, name, *rest = args
        dict_ = {'__builtins__': builtins}
        class_body_result = interp(body_f.code, globals_=dict_, state=state,
                                   in_function=False)
        if class_body_result.is_exception():
            return class_body_result
        guest_class = GuestClass(name, dict_, *rest, **kwargs)
        return Result(guest_class)
    elif isinstance(f, GuestPartial):
        return f.invoke(args, interp=interp_callback)
    elif isinstance(f, GuestBuiltin):
        return f.invoke(args, interp=interp_callback)
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


def import_path(path: Text, fully_qualified: Text,
                state: InterpreterState) -> Result[GuestModule]:
    if COLOR_TRACE_MOD:
        cprint('Importing; path: %r; fq: %r' % (path, fully_qualified),
               color='blue')
    result = import_routines.import_path(path, fully_qualified, interp, state)
    if COLOR_TRACE_MOD:
        cprint('Imported; result: %r' % (result), color='blue')
    return result
