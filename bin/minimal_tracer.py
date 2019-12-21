#!/usr/bin/env python

import dis
import optparse
import os
import sys

from echo import trace_util
from echo.ctype_frame import CtypeFrame


stack = True
opcodeno = 0


def _print_inst(instruction, frame):
    global opcodeno
    if instruction.starts_line:
        print('{}:{}'.format(frame.f_code.co_filename, frame.f_lineno))
    print('{:5d} :: {:3d} {}'.format(opcodeno, instruction.offset, trace_util.remove_at_hex(str(instruction))))
    opcodeno += 1


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
        if stack:
            ctf = CtypeFrame(frame)
            ctf.print_stack(do_localsplus=False, printer=_print_stack)
    elif event == 'return':
        #print('=>', repr(arg), repr(type(arg)))
        pass
    else:
        pass
    return note_trace


def main():
    global stack
    parser = optparse.OptionParser()
    parser.add_option('--nostack', dest='stack', action='store_false', default=True, help='Do not show stack in dump')
    opts, args = parser.parse_args()
    assert len(args) == 1, args
    path = args[0]
    stack = opts.stack
    with open(path) as f:
        contents = f.read()
    globals_ = {'__name__': '__main__'}
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
    exec(code, globals_)


if __name__ == '__main__':
    main()
