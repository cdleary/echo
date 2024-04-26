#!/usr/bin/env python3

import collections
import dis
import optparse
import os
import pprint
import sys
import types

from echo import trace_util
from echo import ctype_frame
from echo import cpython_tracer


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


def _print_inst(instruction: dis.Instruction, frame: types.FrameType) -> None:
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

    if stack and bc_histo is None:
        ctf = ctype_frame.CtypeFrame(frame)
        ctf.print_stack(do_localsplus=False, printer=_print_stack)


def _print_stack(*args):
    print(' ' * 8, *args)


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

    cpython_tracer.trace_path(args[0], _print_inst)

    if opts.bc_histo:
        pprint.pprint(bc_histo.most_common())


if __name__ == '__main__':
    main()
