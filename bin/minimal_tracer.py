#!/usr/bin/env python

import dis
import sys


saw_return = True


def note_trace(frame, event, arg):
    global saw_return
    filename = frame.f_code.co_filename
    #print(repr(event), frame)
    if event == 'call':
        if not filename.startswith('<frozen'):
            frame.f_trace_opcodes = True
            frame.f_trace = note_trace
    elif event == 'opcode':
        if saw_return:
            lineno = frame.f_lineno
            print('{}:{}'.format(filename, lineno))
            saw_return = False
        instructions = dis.get_instructions(frame.f_code)
        instruction = next(inst for inst in instructions
                           if inst.offset == frame.f_lasti)
        print(instruction)
    elif event == 'return':
        print('=>', repr(arg), repr(type(arg)))
        saw_return = True
    else:
        pass


def main():
    path = sys.argv[1]
    with open(path) as f:
        contents = f.read()
    globals_ = {'__name__': '__main__'}
    f = sys._getframe(0)
    sys.settrace(note_trace)
    exec(contents, globals_)


if __name__ == '__main__':
    main()
