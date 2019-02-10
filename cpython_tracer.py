import ctypes
import dis
import inspect
import sys
import types
from typing import Any

import termcolor


class CtypeFrame:
    """Wraps interpreter frame to allow inspection of interpreter-private data.

    Stack inspection inspired by the approach shown in:

        http://code.activestate.com/recipes/578412-peek-at-python-value-stack/
    """

    VERSION_TO_CTYPE_ULONG_OFFSETS = {
        (3, 7): {
            'f_back': 3,
            'f_code': 4,
            'f_builtins': 5,
            'f_globals': 6,
            'f_locals': 7,
            'f_valuestack': 8,
            'f_stacktop': 9,
        },
    }
    ULONG_SIZE_IN_BYTES = 8

    def __init__(self, frame: types.FrameType):
        self.frame_ptr = ctypes.cast(id(frame), ctypes.POINTER(ctypes.c_ulong))
        self.offsets = self.VERSION_TO_CTYPE_ULONG_OFFSETS[
            sys.version_info[:2]]
        for offset in range(30):
            if id(frame.f_back) == self.frame_ptr[offset]:
                self.f_back_offset = offset

    @staticmethod
    def _id2obj(id_: int) -> Any:
        """Mutates a tuple cell to point at a new location."""
        t = (None,)
        try:
            ctypes.cast(id(t), ctypes.POINTER(ctypes.c_ulong))[3] = id_
            return t[0]
        finally:
            # Do we need to do this to keep the refcounts sane?
            ctypes.cast(id(t), ctypes.POINTER(ctypes.c_ulong))[3] = id(None)

    def get_value_stack(self):
        return self.frame_ptr[self.offsets['f_valuestack']]

    def get_value_stack_as_ptr(self):
        return ctypes.cast(self.get_value_stack(),
                           ctypes.POINTER(ctypes.c_ulong))

    def get_stack_top(self):
        return self.frame_ptr[self.offsets['f_stacktop']]

    def print_stack(self):
        # print(' value stack (pyobj**):', self.get_value_stack())
        # print(' stack top (pyobj**):', self.get_stack_top())
        count = self.get_stack_top() - self.get_value_stack()
        assert count % self.ULONG_SIZE_IN_BYTES == 0
        stack_items = count // self.ULONG_SIZE_IN_BYTES
        print(' stack (%d):' % stack_items)
        for i in range(stack_items):
            stack_value = self.get_value_stack_as_ptr()[i]
            # print(' stack value (pyobj*):', stack_value)
            if stack_value == 0:
                print('  TOS%d: <null>' % i)
            else:
                print('  TOS%d:' % i, self._id2obj(stack_value))


def note_trace(frame, event, arg):
    def print_frame_info():
        print(' frame.f_lasti:', frame.f_lasti, file=sys.stderr)
        print(' frame.f_lineno:', frame.f_lineno, file=sys.stderr)
        # print(' frame.f_locals:', frame.f_locals, file=sys.stderr)
    if event == 'call':
        print('call!', file=sys.stderr)
        # Turn on opcode tracing for the frame we're entering.
        frame.f_trace_opcodes = True
    elif event == 'opcode':
        # From the docs:
        #     The interpreter is about to execute a new opcode (see dis for
        #     opcode details). The local trace function is called; arg is None;
        #     the return value specifies the new local trace function.
        #     Per-opcode events are not emitted by default: they must be
        #     explicitly requested by setting f_trace_opcodes to True on the
        #     frame.
        # -- https://docs.python.org/3/library/sys.html#sys.settrace
        print('opcode about to execute...', file=sys.stderr)
        ctf = CtypeFrame(frame)
        print(' frame.f_lasti:', frame.f_lasti, file=sys.stderr)
        instructions = dis.get_instructions(frame.f_code)
        instruction = next(inst for inst in instructions
                           if inst.offset == frame.f_lasti)
        termcolor.cprint(' instruction: {}'.format(instruction),
                         color='yellow')
        print(' stack effect:', dis.stack_effect(instruction.opcode,
              instruction.arg))
        ctf.print_stack()
    elif event == 'line':
        print('line!', file=sys.stderr)
        print_frame_info()
    elif event == 'return':
        pass
    elif event == 'exception':
        pass
    else:
        print('unhandled event:', event)
        sys.exit(-1)

    return note_trace


def main():
    path = sys.argv[1]
    print('Reading path:', path, file=sys.stderr)
    with open(path) as f:
        contents = f.read()

    sys.settrace(note_trace)
    globals_ = {}
    exec(contents, globals_)


if __name__ == '__main__':
    main()
