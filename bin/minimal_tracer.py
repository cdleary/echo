#!/usr/bin/env python3

import collections
import dis
import optparse
import os
import pprint
import sys

from echo import trace_util
from echo import ctype_frame


stack = True
opcodeno = 0
limit = None
show_opcodeno = True
bc_histo = None


def get_histo_name(instruction, frame):
    if instruction.opname == 'COMPARE_OP':
        ctf = ctype_frame.CtypeFrame(frame)
        rhs = ctf.get_tos_value(0)
        lhs = ctf.get_tos_value(1)
        cmp = instruction.argval.replace(' ', '_')
        return f'{instruction.opname}__{cmp}__{type(lhs).__name__}__{type(rhs).__name__}'
    if instruction.opname in ('BINARY_AND', 'BINARY_ADD', 'BINARY_SUBTRACT',
                              'BINARY_SUBSCR', 'INPLACE_ADD', 'LIST_APPEND',
                              'BINARY_MODULO', 'BINARY_MULTIPLY', 'BINARY_TRUE_DIVIDE'):
        ctf = ctype_frame.CtypeFrame(frame)
        rhs = ctf.get_tos_value(0)
        lhs = ctf.get_tos_value(1)
        return f'{instruction.opname}__{type(lhs).__name__}__{type(rhs).__name__}'
    if instruction.opname in ('LOAD_ATTR', 'LOAD_METHOD'):
        ctf = ctype_frame.CtypeFrame(frame)
        lhs = ctf.get_tos_value(0)
        return f'{instruction.opname}__{type(lhs).__name__}__{instruction.argval}'
    if instruction.opname in ('FOR_ITER', 'GET_ITER', 'UNARY_NOT', 'UNARY_INVERT'):
        ctf = ctype_frame.CtypeFrame(frame)
        lhs = ctf.get_tos_value(0)
        return f'{instruction.opname}__{type(lhs).__name__}'
    return instruction.opname


def _print_inst(instruction, frame):
    global opcodeno
    if bc_histo is not None:
        bc_histo[get_histo_name(instruction, frame)] += 1
        return
    if instruction.starts_line:
        print('{}:{} :: {}'.format(frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name))
    opcode_leader = '{:5d} :: '.format(opcodeno) if show_opcodeno else ''
    print('{}{:3d} {}'.format(opcode_leader, instruction.offset, trace_util.remove_at_hex(str(instruction))))
    opcodeno += 1
    if limit is not None and opcodeno > limit:
        sys.exit(0)


def _print_stack(*args):
    print(' ' * 8, *args)


def note_trace(frame, event, arg):
    filename = frame.f_code.co_filename
    if filename.startswith('<frozen'):
        return note_trace

    frame.f_trace_opcodes = True
    frame.f_trace = note_trace
    #print(repr(event), frame)
    if event == 'call':
        #print(repr(event), frame)
        pass
    elif event == 'opcode':
        instructions = dis.get_instructions(frame.f_code)
        instruction = next(inst for inst in instructions
                           if inst.offset == frame.f_lasti)
        _print_inst(instruction, frame)
        if instruction.opname == 'EXTENDED_ARG':
            # For some reason the opcode after the extended arg doesn't seem
            # to get traced.
            instruction2 = next(inst for inst in instructions
                               if inst.offset > frame.f_lasti)
            _print_inst(instruction2, frame)
        if stack and bc_histo is None:
            ctf = ctype_frame.CtypeFrame(frame)
            ctf.print_stack(do_localsplus=False, printer=_print_stack)
    elif event == 'return':
        #print('=>', repr(arg), repr(type(arg)))
        pass
    else:
        pass
    return note_trace


def main():
    global stack, limit, show_opcodeno, bc_histo
    parser = optparse.OptionParser()
    parser.add_option('--nostack', dest='stack', action='store_false', default=True, help='Do not show stack in dump')
    parser.add_option('--noopcodeno', dest='opcodeno', action='store_false', default=True, help='Do not show opcodeno in dump')
    parser.add_option('--limit', type=int, help='Limit opcode count to run')
    parser.add_option('--bc_histo', action='store_true', default=False)
    opts, args = parser.parse_args()
    path = args[0]
    if opts.bc_histo:
        bc_histo = collections.Counter()
    stack = opts.stack
    limit = opts.limit
    show_opcodeno = opts.opcodeno

    sys.argv = args
    with open(path) as f:
        contents = f.read()
    globals_ = {'__name__': '__main__', '__file__': os.path.realpath(path)}
    #del sys.modules['enum']
    #del sys.modules['re']
    #del sys.modules['sre_compile']
    #del sys.modules['sre_parse']
    #del sys.modules['sre_constants']
    #del sys.modules['types']
    #sys.modules.pop('collections')
    f = sys._getframe(0)
    code = compile(contents, os.path.realpath(path), 'exec')
    sys.settrace(note_trace)
    try:
        exec(code, globals_)
    finally:
        sys.settrace(None)
    if opts.bc_histo:
        pprint.pprint(bc_histo.most_common())


if __name__ == '__main__':
    main()
