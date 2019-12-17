#!/usr/bin/env python

import dis
import os
import sys

from echo import trace_util


def note_trace(frame, event, arg):
    filename = frame.f_code.co_filename
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
        if instruction.starts_line:
            lineno = frame.f_lineno
            print('{}:{}'.format(filename, lineno))
        print(trace_util.remove_at_hex(str(instruction)))
    elif event == 'return':
        #print('=>', repr(arg), repr(type(arg)))
        pass
    else:
        pass
    return note_trace


def main():
    path = sys.argv[1]
    with open(path) as f:
        contents = f.read()
    globals_ = {'__name__': '__main__'}
    f = sys._getframe(0)
    code = compile(contents, os.path.realpath(path), 'exec')
    sys.settrace(note_trace)
    exec(code, globals_)


if __name__ == '__main__':
    main()
