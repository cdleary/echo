"""(Metacircular) interpreter loop implementation.

Notes
-----

co_flags:

* 0x04: function uses *args
* 0x08: function uses **kwargs
* 0x20: generator function
"""


import dis
import functools
import logging
import operator
import types

from io import StringIO
from typing import Dict, Any, Text, Tuple, List, Optional, Union

from common import dis_to_str, get_code


STARARGS_FLAG = 0x04
_BINARY_OPS = {
    'BINARY_ADD': operator.add,
    'BINARY_MODULO': operator.mod,
    'BINARY_MULTIPLY': operator.mul,
    'BINARY_SUBSCR': operator.getitem,
}
_COMPARE_OPS = {
    '==': operator.eq,
}
_BUILTIN_TYPES = {
    int,
    list,
}
_CODE_ATTRS = [
    'co_argcount', 'co_cellvars', 'co_code', 'co_consts', 'co_filename',
    'co_firstlineno', 'co_flags', 'co_freevars', 'co_kwonlyargcount',
    'co_lnotab', 'co_name', 'co_names', 'co_nlocals', 'co_stacksize',
    'co_varnames',
]


class GuestFunction(object):
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

    def invoke(self, args: Tuple[Any, ...]) -> Any:
        return interp(self.code, self.globals_, args, self.defaults,
                      self.closure, in_function=True)


class GuestPartial(object):
    def __init__(self, f: GuestFunction, args: Tuple[Any, ...]):
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

    def get(self):
        assert self._storage is not GuestCell, (
            'GuestCell %r is uninitialized' % self._name)
        return self._storage

    def set(self, value):
        self._storage = value


def interp(code: types.CodeType, globals_: Dict[Text, Any],
           args: Optional[Tuple[Any, ...]] = None,
           defaults: Optional[Tuple[Any, ...]] = None,
           closure: Optional[Tuple[GuestCell, ...]] = None,
           in_function: bool = True) -> Any:
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
    stack = []
    consts = code.co_consts  # LOAD_CONST indexes into this.
    names = code.co_names  # LOAD_GLOBAL uses these names.

    # TODO(cdleary, 2019-01-21): Investigate why this "builtins" ref is
    # sometimes a dict and other times a module?
    builtins = globals_['__builtins__']

    def push(x): stack.append(x)

    def pop(): return stack.pop()

    def pop_n(n: int, tos_is_0: bool = True) -> List[Any]:
        nonlocal stack
        stack, result = stack[:-n], stack[-n:]
        if tos_is_0:
            return list(reversed(result))
        return result

    def peek(): return stack[-1]

    def get_global_or_builtin(name):
        try:
            return globals_[name]
        except KeyError:
            return builtins_get(builtins, name)

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
    pc = 0
    while True:
        instruction = pc_to_instruction[pc]
        logging.debug('Running @%d %s :: %s:', pc, instruction, stack)
        opname = instruction.opname
        if opname == 'SETUP_LOOP':
            pass
        elif opname == 'LOAD_GLOBAL':
            namei = instruction.arg
            name = names[namei]
            push(get_global_or_builtin(name))
        elif opname == 'LOAD_CONST':
            push(consts[instruction.arg])
        elif opname == 'CALL_FUNCTION':
            argc = instruction.arg
            f_pos = -argc-1
            stack, f, args = stack[:f_pos], stack[f_pos], tuple(stack[-argc:])
            if f is range:
                push(range(*args))
            elif f is print:
                result = print(*args)
                push(result)
            elif isinstance(f, GuestFunction):
                push(interp(f.code, globals_, args=args, closure=f.closure))
            elif isinstance(f, types.FunctionType):
                push(interp(f.__code__, f.__globals__, defaults=f.__defaults__,
                            args=args))
            # TODO(cdleary, 2019-01-22): Consider using an import hook to avoid
            # the C-extension version of functools from being imported so we
            # don't need to consider it specially.
            elif f is functools.partial:
                push(GuestPartial(args[0], args[1:]))
            elif isinstance(f, GuestPartial):
                push(f.invoke(args))
            else:
                raise NotImplementedError(f, args)
        elif opname == 'CALL_FUNCTION_KW':
            args = instruction.arg
            kwarg_names = pop()
            kwarg_values = pop_n(len(kwarg_names), tos_is_0=True)
            assert len(kwarg_names) == len(kwarg_values), (
                kwarg_names, kwarg_values)
            kwargs = list(zip(kwarg_names, kwarg_values))
            rest = args-len(kwargs)
            args = pop_n(rest, tos_is_0=False)
            to_call = pop()
            raise NotImplementedError(to_call)
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
        elif opname == 'POP_TOP':
            pop()
        elif opname == 'POP_BLOCK':
            pass  # Ignoring blocks for now.
        elif opname == 'JUMP_ABSOLUTE':
            pc = instruction.arg
            continue
        elif opname == 'POP_JUMP_IF_FALSE':
            if is_false(pop()):
                pc = instruction.arg
                continue
        elif opname == 'RETURN_VALUE':
            return pop()
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
        elif opname == 'BUILD_LIST':
            count = instruction.arg
            stack, t = stack[:-count], stack[-count:]
            push(t)
        elif opname.startswith('BINARY'):
            # Probably need to handle radd and such here.
            op = _BINARY_OPS[opname]
            rhs = pop()
            lhs = pop()
            if {type(lhs), type(rhs)} <= _BUILTIN_TYPES:
                push(op(lhs, rhs))
            else:
                raise NotImplementedError(lhs, rhs)
        elif opname == 'COMPARE_OP':
            op = _COMPARE_OPS[instruction.argval]
            lhs = pop()
            rhs = pop()
            if type(lhs) is int and type(rhs) is int:
                push(op(lhs, rhs))
            else:
                raise NotImplementedError(lhs, rhs)
        elif opname == 'IMPORT_NAME':
            # TODO(leary, 2019-01-21): Use fromlist/level.
            fromlist = pop()
            level = pop()
            push(__import__(instruction.argval, globals_))
        elif opname == 'IMPORT_FROM':
            module = peek()
            assert isinstance(module, types.ModuleType), module
            push(getattr(module, instruction.argval))
        elif opname == 'LOAD_ATTR':
            obj = pop()
            push(getattr(obj, instruction.argval))
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
        elif opname == 'LOAD_CLOSURE':
            push(cellvars[instruction.arg])
        elif opname == 'INPLACE_ADD':
            lhs = pop()
            rhs = pop()
            if type(lhs) is int and type(rhs) is int:
                push(operator.add(lhs, rhs))
            else:
                raise NotImplementedError(instruction, stack)
        elif opname == 'DUP_TOP_TWO':
            stack = stack + stack[-2:]
        elif opname == 'ROT_THREE':
            #                                  old first  old second  old third
            stack[-3], stack[-1], stack[-2] = stack[-1], stack[-2], stack[-3]
        else:
            raise NotImplementedError(instruction, stack)
        pc += pc_to_bc_width[pc]


def run_function(f: types.FunctionType, *args: Tuple[Any, ...],
                 globals_=None) -> Any:
    globals_ = globals_ or globals()
    return interp(get_code(f), globals_, defaults=f.__defaults__, args=args)
