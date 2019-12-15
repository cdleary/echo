#!/usr/bin/env python

import sys

def note_trace(frame, event, arg):
    #print(repr(event), frame)
    if event == 'call':
        filename = frame.f_code.co_filename
        if not filename.startswith('<frozen'):
            lineno = frame.f_lineno
            print('{}:{}'.format(filename, lineno))
    elif event == 'opcode':
        print(frame.f_lasti)
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
