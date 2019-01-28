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
from typing import (Dict, Any, Text, Tuple, List, Optional, Union, TypeVar,
                    Generic, Sequence, Iterable)

import termcolor

from common import dis_to_str, get_code


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


class ResultKind(Enum):
    VALUE = 'value'
    EXCEPTION = 'exception'


T = TypeVar('T')
ExceptionData = collections.namedtuple('ExceptionData',
                                       'traceback parameter exception')


class Result(Generic[T]):

    def __init__(self, value: Union[T, ExceptionData]):
        self.value = value

    def is_exception(self) -> bool:
        return isinstance(self.value, ExceptionData)

    def get_value(self) -> T:
        assert not isinstance(self.value, ExceptionData)
        return self.value

    def get_exception(self) -> ExceptionData:
        assert isinstance(self.value, ExceptionData)
        return self.value


class GuestPyObject:

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def getattr(self, name: Text) -> Any:
        raise NotImplementedError(self, name)

    @abc.abstractmethod
    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


class GuestModule(GuestPyObject):
    def __init__(self, name: Text, code, globals_: Dict[Text, Any]):
        self.name = name
        self.code = code
        self.globals_ = globals_

    def keys(self) -> Iterable[Text]:
        return self.globals_.keys()

    def getattr(self, name: Text) -> Any:
        return self.globals_[name]


class GuestFunction(GuestPyObject):
    def __init__(self, code, globals_, name, *, defaults=None, closure=None):
        self.code = code
        self.globals_ = globals_
        self.name = name
        self.defaults = defaults
        self.closure = closure

    def __repr__(self):
        return ('_Function(code={!r}, name={!r}, closure={!r}, '
                'defaults={!r})').format(
                    self.code, self.name, self.closure, self.defaults)

    def invoke(self, args: Tuple[Any, ...]) -> Result[Any]:
        return interp(self.code, self.globals_, args, self.defaults,
                      self.closure, in_function=True)

    def getattr(self, name: Text) -> Any:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestInstance(GuestPyObject):

    def __init__(self, cls: 'GuestClass'):
        self.cls = cls
        self.dict = {}

    def getattr(self, name: Text) -> Any:
        return self.dict[name]

    def setattr(self, name: Text, value: Any):
        self.dict[name] = value


class GuestClass(GuestPyObject):
    def __init__(self, name, dict_, bases=None, metaclass=None, kwargs=None):
        self.name = name
        self.dict_ = dict_
        self.bases = bases or ()
        self.metaclass = metaclass
        self.kwargs = kwargs

    def __repr__(self) -> Text:
        return 'GuestClass(name={!r}, ...)'.format(self.name)

    def instantiate(self, args: Tuple[Any, ...],
                    globals_: Dict[Text, Any]) -> Result[GuestInstance]:
        guest_instance = GuestInstance(self)
        if '__init__' in self.dict_:
            init_f = self.dict_['__init__']
            # TODO(cdleary, 2019-01-26) What does Python do when you return
            # something non-None from initializer? Ignore?
            result = do_call(init_f, args=(guest_instance,) + args,
                             globals_=globals_)
            if result.is_exception():
                return result
        return Result(guest_instance)

    def getattr(self, name: Text) -> Any:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestBuiltin(GuestPyObject):
    def __init__(self, name: Text, bound_self: Any):
        self.name = name
        self.bound_self = bound_self

    def __repr__(self):
        return 'GuestBuiltin(name={!r}, ...)'.format(self.name)

    def invoke(self, args: Tuple[Any, ...]) -> Result[Any]:
        if self.name == 'dict.keys':
            assert not args, args
            return Result(self.bound_self.keys())
        else:
            raise NotImplementedError(self.name)

    def getattr(self, name: Text) -> Any:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestPartial(object):
    def __init__(self, f: GuestFunction, args: Tuple[Any, ...]):
        assert isinstance(f, GuestFunction), f
        self.f = f
        self.args = args

    def invoke(self, args: Tuple[Any, ...]) -> Any:
        return self.f.invoke(self.args + args)


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
        termcolor.cprint('%05d: ' % lineno, color='yellow', end='')
        termcolor.cprint(line.rstrip(), color='blue')


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


def interp(code: types.CodeType,
           globals_: Dict[Text, Any],
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

    if COLOR_TRACE:
        def gprint(*args): termcolor.cprint(*args, color='green')
        gprint('interpreting:')
        gprint('  co_name:     %r' % code.co_name)
        gprint('  co_argcount: %d' % code.co_argcount)
        gprint('  co_nlocals:  %d' % code.co_nlocals)
        gprint('  co_cellvars: %r' % (code.co_cellvars,))
        gprint('  co_freevars: %r' % (code.co_freevars,))
        gprint('  co_varnames: %r' % (code.co_varnames,))
        gprint('  co_names:    %r' % (code.co_names,))
        gprint('  closure:     %r' % (closure,))
        gprint('  len(args):   %d' % len(args))
        gprint('  loc:         %s:%d' % (code.co_filename,
                                         code.co_firstlineno))
        cprint_lines_after(code.co_filename, code.co_firstlineno)

    # TODO(cdleary, 2019-01-21): Investigate why this "builtins" ref is
    # sometimes a dict and other times a module?
    builtins = globals_['__builtins__']

    def push(x):
        if COLOR_TRACE:
            termcolor.cprint(' =(push)=> %r [depth after: %d]' %
                             (x, len(stack)+1), color='blue')
        assert not isinstance(x, Result), x
        stack.append(x)

    def pop():
        x = stack.pop()
        if COLOR_TRACE:
            termcolor.cprint(' <=(pop)= %r [depth after: %d]' %
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
            termcolor.cprint(' ! moved PC to %d' % pc,
                             color='magenta')
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
    while True:
        instruction = pc_to_instruction[pc]
        if COLOR_TRACE:
            termcolor.cprint('%4d: %s' % (pc, instruction), color='yellow')
        opname = instruction.opname
        if opname == 'SETUP_LOOP':
            block_stack.append(('loop',
                                instruction.arg + pc + pc_to_bc_width[pc]))
        elif opname == 'EXTENDED_ARG':
            pass  # The to-instruction decoding step already extended the args?
        elif opname == 'SETUP_EXCEPT':
            block_stack.append(('except',
                                instruction.arg+pc+pc_to_bc_width[pc]))
        elif opname == 'POP_EXCEPT':
            popped = block_stack.pop()
            assert popped[0] == 'except', 'Popped non-except block.'
        elif opname == 'END_FINALLY':
            # From the Python docs: "The interpreter recalls whether the
            # exception has to be re-raised, or whether the function returns,
            # and continues with the outer-next block."
            raise NotImplementedError
        elif opname == 'RAISE_VARARGS':
            argc = instruction.arg
            traceback, parameter, exception = (None, None, None)
            if argc > 2:
                traceback = pop()
            if argc > 1:
                parameter = pop()
            if argc > 0:
                exception = pop()
            if COLOR_TRACE:
                termcolor.cprint(' ! exception %r %r %r' % (
                                    traceback, parameter, exception),
                                 color='magenta')
            exception_data = ExceptionData(traceback, parameter, exception)
            if handle_exception():
                continue
            else:
                return Result(exception_data)
        elif opname == 'LOAD_GLOBAL':
            namei = instruction.arg
            name = names[namei]
            push(get_global_or_builtin(name))
        elif opname == 'LOAD_CONST':
            push(consts[instruction.arg])
        elif opname == 'CALL_FUNCTION':
            # As of Python 3.6 this only supports calls for functions with
            # positional arguments.
            if sys.version_info >= (3, 6):
                argc = instruction.arg
                kwargc = 0
            else:
                argc = instruction.arg & 0xff
                kwargc = instruction.arg >> 8
            kwarg_stack = pop_n(2 * kwargc, tos_is_0=False)
            kwargs = dict(zip(kwarg_stack[::2], kwarg_stack[1::2]))
            args = pop_n(argc, tos_is_0=False)
            f = pop()
            result = do_call(f, args, kwargs=kwargs, globals_=globals_)
            if result.is_exception():
                exception_data = result.get_exception()
                if COLOR_TRACE:
                    termcolor.cprint(' =(call exception)=> %r' % (
                                        exception_data,), color='magenta')
                if handle_exception():
                    continue
                else:
                    return result
            else:
                push(result.get_value())
        elif opname == 'CALL_FUNCTION_KW':
            args = instruction.arg
            kwarg_names = pop()
            kwarg_values = pop_n(len(kwarg_names), tos_is_0=True)
            assert len(kwarg_names) == len(kwarg_values), (
                kwarg_names, kwarg_values)
            kwargs = dict(zip(kwarg_names, kwarg_values))
            rest = args-len(kwargs)
            args = pop_n(rest, tos_is_0=False)
            to_call = pop()
            result = do_call(to_call, args, kwargs=kwargs, globals_=globals_)
            if result.is_exception():
                raise NotImplementedError
            else:
                push(result.get_value())
        elif opname == 'CALL_FUNCTION_EX':
            arg = instruction.arg
            if arg & 0x1:
                kwargs = pop()
            else:
                kwargs = None
            callargs = pop()
            func = pop()
            result = do_call(func, callargs, kwargs=kwargs, globals_=globals_)
            if result.is_exception():
                raise NotImplementedError
            else:
                push(result.get_value())
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
        elif opname == 'STORE_FAST':
            locals_[instruction.arg] = pop()
        elif opname == 'STORE_NAME':
            if in_function:
                locals_[instruction.arg] = pop()
            else:
                globals_[instruction.argval] = pop()
        elif opname == 'LOAD_FAST':
            push(locals_[instruction.arg])
        elif opname == 'LOAD_BUILD_CLASS':
            push(builtins_get(builtins, '__build_class__'))
        elif opname == 'POP_TOP':
            pop()
        elif opname == 'POP_BLOCK':
            block_stack.pop()
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
        elif opname == 'MAKE_FUNCTION':
            qualified_name = pop()
            code = pop()
            closure = None
            defaults = None
            if instruction.arg & 0x08:
                assert isinstance(peek(), tuple), peek()
                closure = pop()
            if instruction.arg & 0x04:
                raise NotImplementedError
            if instruction.arg & 0x02:
                raise NotImplementedError
            if instruction.arg & 0x01:
                defaults = pop()
            f = GuestFunction(code, globals_, qualified_name,
                              defaults=defaults, closure=closure)
            push(f)
        elif opname == 'BUILD_TUPLE':
            count = instruction.arg
            stack, t = stack[:-count], tuple(stack[-count:])
            push(t)
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
        elif opname == 'COMPARE_OP':
            rhs = pop()
            lhs = pop()
            if instruction.argval in ('in', 'not in'):
                op = ((lambda x, y: operator.contains(x, y))
                      if instruction.argval == 'in'
                      else lambda x, y: not operator.contains(x, y))
                if type(rhs) in (list, dict, set):
                    push(op(rhs, lhs))
                else:
                    raise NotImplementedError(lhs, rhs)
            elif instruction.argval == 'exception match':
                push(_exception_match(lhs, rhs))
            else:
                op = _COMPARE_OPS[instruction.argval]
                types_ = {type(lhs), type(rhs)}
                if types_ <= _BUILTIN_TYPES:
                    push(op(lhs, rhs))
                elif (isinstance(lhs, GuestInstance) and
                      isinstance(rhs, GuestInstance) and
                      instruction.argval in ('is not', 'is')):
                    push(op(lhs, rhs))
                else:
                    raise NotImplementedError(lhs, rhs)
        elif opname == 'IMPORT_NAME':
            # TODO(leary, 2019-01-21): Use fromlist/level.
            fromlist = pop()
            level = pop()
            result = do_import(instruction.argval, globals_)
            if result.is_exception():
                exception_data = result.get_exception()
                if handle_exception():
                    continue
                else:
                    return result
            else:
                push(result.get_value())
        elif opname == 'IMPORT_STAR':
            module = peek()
            for name in module.keys():
                if not name.startswith('_'):
                    globals_[name] = module.getattr(name)
            pop()  # Docs say 'module is popped after loading all names'.
        elif opname == 'IMPORT_FROM':
            module = peek()
            if isinstance(module, types.ModuleType):
                push(getattr(module, instruction.argval))
            elif isinstance(module, GuestModule):
                push(module.getattr(instruction.argval))
            else:
                raise NotImplementedError(module)
        elif opname == 'LOAD_ATTR':
            obj = pop()
            if isinstance(obj, dict) and instruction.argval == 'keys':
                push(GuestBuiltin('dict.keys', bound_self=obj))
            elif isinstance(obj, GuestPyObject):
                push(obj.getattr(instruction.argval))
            else:
                push(getattr(obj, instruction.argval))
        elif opname == 'STORE_ATTR':
            obj = pop()
            value = pop()
            if isinstance(obj, GuestPyObject):
                obj.setattr(instruction.argval, value)
            else:
                raise NotImplementedError
        elif opname == 'LOAD_NAME':
            if in_function:
                raise NotImplementedError
            else:
                push(get_global_or_builtin(instruction.argval))
        elif opname == 'LOAD_DEREF':
            push(cellvars[instruction.arg].get())
        elif opname == 'STORE_DEREF':
            cellvars[instruction.arg].set(pop())
        elif opname == 'STORE_SUBSCR':
            tos = pop()
            tos1 = pop()
            tos2 = pop()
            operator.setitem(tos1, tos, tos2)
        elif opname == 'MAKE_CLOSURE':
            # Note: this bytecode was removed in Python 3.6.
            name = pop()
            code = pop()
            freevar_cells = pop()
            defaults = pop_n(instruction.arg)
            f = GuestFunction(code, globals_, name, defaults=defaults,
                              closure=freevar_cells)
            push(f)
        elif opname == 'LOAD_CLOSURE':
            cellvar = cellvars[instruction.arg]
            push(cellvar)
        elif opname == 'INPLACE_ADD':
            lhs = pop()
            rhs = pop()
            if {type(lhs), type(rhs)} <= _BUILTIN_TYPES:
                result = _run_binop('BINARY_ADD', lhs, rhs)
                if result.is_exception():
                    raise NotImplementedError
                else:
                    push(result.get_value())
            else:
                raise NotImplementedError(instruction, lhs, rhs)
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
    if kwargs:
        raise NotImplementedError(kwargs)
    guest_partial = GuestPartial(args[0], args[1:])
    return Result(guest_partial)


def do_call(f, args: Tuple[Any, ...],
            *,
            globals_: Dict[Text, Any],
            kwargs: Optional[Dict[Text, Any]] = None) -> Result[Any]:
    kwargs = kwargs or {}
    if f in (dict, range, print, sorted, str, list, ValueError):
        return Result(f(*args, **kwargs))
    if f is globals:
        return Result(globals_)
    elif isinstance(f, GuestFunction):
        return interp(f.code, globals_=f.globals_, args=args, kwargs=kwargs,
                      closure=f.closure)
    elif isinstance(f, types.FunctionType):
        return interp(f.__code__, f.__globals__, defaults=f.__defaults__,
                      args=args, kwargs=kwargs)
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
        class_body_result = interp(body_f.code, dict_, in_function=False)
        if class_body_result.is_exception():
            return class_body_result
        guest_class = GuestClass(name, dict_, *rest, **kwargs)
        return Result(guest_class)
    elif isinstance(f, GuestPartial):
        return f.invoke(args)
    elif isinstance(f, GuestBuiltin):
        return f.invoke(args)
    elif isinstance(f, GuestClass):
        return f.instantiate(args, globals_)
    else:
        raise NotImplementedError(f, args, kwargs)


def import_path(path: Text) -> Result[GuestModule]:
    fullpath = path
    path, basename = os.path.split(fullpath)
    module_name, _ = os.path.splitext(basename)
    # Note: if we import the module it'll execute via the host interpreter.
    #
    # Instead, we need to go through the steps ourselves (read file, parse to
    # AST, bytecode emit, interpret bytecode).
    with open(fullpath) as f:
        contents = f.read()

    module_code = compile(contents, fullpath, 'exec')
    assert isinstance(module_code, types.CodeType), module_code

    globals_ = {'__builtins__': builtins}
    interp(module_code, globals_, in_function=False)
    return Result(GuestModule(module_name, module_code, globals_))


def _find_module_path(search_path: Text,
                      pieces: Sequence[Text]) -> Optional[Text]:
    *leaders, last = pieces
    candidate = os.path.join(search_path, *leaders)
    logging.debug('Candidate: %r', candidate)
    if os.path.exists(candidate):
        if os.path.isdir(os.path.join(candidate, last)):
            init_path = os.path.join(candidate, last, '__init__.py')
            if os.path.exists(init_path):
                return init_path
        target = os.path.join(candidate, last + '.py')
        if os.path.exists(target):
            return target
    return None


def find_module_path(name: Text) -> Optional[Text]:
    pieces = name.split('.')

    for search_path in sys.path:
        result = _find_module_path(search_path, pieces)
        if result:
            return result
    return None


def do_import(name: Text,
              globals_: Dict[Text, Any]) -> Result[
                Union[types.ModuleType, GuestModule]]:
    def import_error(name: Text) -> Result[Any]:
        return Result(ExceptionData(
            None,
            'Could not find module with name {!r}'.format(name),
            ImportError))

    if name in ('functools', 'os', 'itertools', 'builtins'):
        module = __import__(name, globals_)  # type: types.ModuleType
    else:
        path = find_module_path(name)
        if path is None:
            return import_error(name)
        else:
            result = import_path(path)
            if result.is_exception():
                raise NotImplementedError
            module = result.get_value()
    return Result(module)


def run_function(f: types.FunctionType, *args: Tuple[Any, ...],
                 globals_=None) -> Any:
    """Interprets f in the echo interpreter, returns unwrapped result."""
    globals_ = globals_ or globals()
    result = interp(get_code(f), globals_, defaults=f.__defaults__, args=args)
    return result.get_value()
