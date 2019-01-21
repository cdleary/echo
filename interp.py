"""(Metacircular) interpreter loop implementation.

Notes
-----

co_flags:

* 0x04: function uses *args
* 0x08: function uses **kwargs
* 0x20: generator function
"""


import dis
import logging
import operator
import types

from io import StringIO
from typing import Dict, Any, Text, Tuple, List, Optional

from common import dis_to_str, get_code


STARARGS_FLAG = 0x04
_BINARY_OPS = {
    'BINARY_ADD': operator.add,
    'BINARY_MODULO': operator.mod,
    'BINARY_MULTIPLY': operator.mul,
}
_COMPARE_OPS = {
    '==': operator.eq,
}


class _Function(object):
    def __init__(self, code, name):
        self.code = code
        self.name = name


def is_false(v: Any) -> bool:
    if isinstance(v, int):
        return v == 0
    if isinstance(v, bool):
        return v == False
    else:
        raise NotImplementedError(v)


def code_to_str(c: types.CodeType) -> Text:
    _CODE_ATTRS = ['co_argcount', 'co_cellvars', 'co_code', 'co_consts', 'co_filename', 'co_firstlineno', 'co_flags', 'co_freevars', 'co_kwonlyargcount', 'co_lnotab', 'co_name', 'co_names', 'co_nlocals', 'co_stacksize', 'co_varnames']
    guts = ', '.join('{}={!r}'.format(attr.split('_')[1], getattr(c, attr)) for attr in _CODE_ATTRS)
    return 'Code({})'.format(guts)


def interp(code: types.CodeType, globals_: Dict[Text, Any],
           args: Tuple[Any, ...] = (),
           defaults: Tuple[Any, ...] = (),
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
    TODO(cdleary, 2019-01-21): Use dis.stack_effect to cross-check stack depth change.
    """
    logging.debug('<bytecode>')
    logging.debug(dis_to_str(code))
    logging.debug('</bytecode>')
    logging.debug(code_to_str(code))

    # Note: co_argcount includes default arguments in the count.
    assert len(args) + len(defaults) >= code.co_argcount or code.co_flags & STARARGS_FLAG, (code, args, defaults, code.co_argcount)

    locals_ = list(args) + list(defaults) + [None] * (code.co_nlocals-code.co_argcount)
    stack = []
    consts = code.co_consts  # LOAD_CONST indexes into this.
    names = code.co_names  # LOAD_GLOBAL uses these names.
    builtins = globals_['__builtins__']
    #assert isinstance(builtins, types.ModuleType), builtins
    push = lambda x: stack.append(x)
    pop = lambda: stack.pop()
    peek = lambda: stack[-1]
    instructions = tuple(dis.get_instructions(code))
    pc_to_instruction = [None] * (instructions[-1].offset+1)  # type: List[Optional[dis.Instruction]]
    pc_to_bc_width = [None] * (instructions[-1].offset+1)  # type: List[Optional[int]]
    for i, instruction in enumerate(instructions):
        pc_to_instruction[instruction.offset] = instruction
        if i+1 != len(instructions):
            pc_to_bc_width[instruction.offset] = instructions[i+1].offset-instruction.offset
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
            try:
                push(globals_[name])
            except KeyError:
                push(builtins[name])
        elif opname == 'LOAD_CONST':
            push(consts[instruction.arg])
        elif opname == 'CALL_FUNCTION':
            argc = instruction.arg
            f_pos = -argc-1
            stack, f, args = stack[:f_pos], stack[f_pos], stack[-argc:]
            if f is range:
                push(range(*args))
            elif f is print:
                result = print(*args)
                push(result)
            elif isinstance(f, _Function):
                push(interp(f.code, globals_, args=args))
            elif isinstance(f, types.FunctionType):
                push(interp(f.__code__, globals_, args=args))
            else:
                raise NotImplementedError(f, args)
        elif opname == 'GET_ITER':
            push(pop().__iter__())
        elif opname == 'FOR_ITER':
            try:
                push(peek().__next__())
            except StopIteration:
                pop()
                pc += pc_to_bc_width[pc] + instruction.arg
                assert pc_to_instruction[pc].is_jump_target, (pc, pc_to_instruction[pc])
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
            push(_Function(code, qualified_name))
        elif opname == 'BUILD_TUPLE':
            count = instruction.arg
            stack, t = stack[:-count], tuple(stack[-count:])
            push(t)
        elif opname.startswith('BINARY'):
            # Probably need to handle radd and such here.
            op = _BINARY_OPS[opname]
            rhs = pop()
            lhs = pop()
            if type(lhs) is int and type(rhs) is int:
                push(op(lhs,rhs))
            else:
                raise NotImplementedError(lhs, rhs)
        elif opname == 'COMPARE_OP':
            op = _COMPARE_OPS[instruction.argval]
            lhs = pop()
            rhs = pop()
            if type(lhs) is int and type(rhs) is int:
                push(op(lhs,rhs))
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
                push(globals_[instruction.argval])
        else:
            raise NotImplementedError(instruction, stack)
        pc += pc_to_bc_width[pc]


def run_function(f: types.FunctionType, *args: Tuple[Any, ...], globals_=None) -> Any:
    globals_ = globals_ or globals()
    return interp(get_code(f), globals_, defaults=f.__defaults__, args=args)
