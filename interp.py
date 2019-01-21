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

from common import dis_to_str


STARARGS_FLAG = 0x04
_BINARY_OPS = {
    'BINARY_ADD': operator.add,
    'BINARY_MODULO': operator.mod,
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


def interp(code: types.CodeType, globals_: Dict[Text, Any],
           args: Tuple[Any, ...] = ()) -> Any:
    """Evaluates "code" using "globals_" after initializing locals with "args".

    Returns the result of evaluating the code object.

    Implementation note: this is one giant function for the moment, unclear
    whether performance will be important, but this makes it easy for early
    prototyping.

    TODO(cdleary, 2019-01-20): factor.
    """
    logging.debug('<bytecode>')
    logging.debug(dis_to_str(code))
    logging.debug('</bytecode>')
    assert len(args) == code.co_argcount or code.co_flags & STARARGS_FLAG
    locals_ = list(args) + [None] * (code.co_nlocals-code.co_argcount)
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
                #import pdb; pdb.set_trace()
                result = print(*args)
                push(result)
            elif isinstance(f, _Function):
                push(interp(f.code, globals_, args=args))
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
        else:
            raise NotImplementedError(instruction, stack)
        pc += pc_to_bc_width[pc]
