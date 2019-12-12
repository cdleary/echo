#!/usr/bin/env python3

import collections
import ctypes
import dis
import functools
import inspect
import optparse
import pprint
import sys
import types
from typing import Any, cast

import termcolor

from echo import bytecode_trace


OPCODE_COUNT = 0


class CountingTraceDumper:

    def __init__(self):
        self.counts = collections.Counter()
        self.leaf_calls = collections.Counter()
        self.code_stack = []

    def note_call(self, code):
        if self.code_stack:
            self.code_stack[-1][1] = True
        self.code_stack.append([code, False])

    def note_block_stack(self, bs):
        pass

    def note_return(self, code):
        this_code, saw_call = self.code_stack.pop()
        assert this_code is code
        if not saw_call:
            self.leaf_calls[code] += 1

    def note_instruction(self, i: dis.Instruction, ctf: 'CtypeFrame'):
        opname = i.opname
        if opname in ('LOAD_ATTR', 'LOAD_METHOD', 'FOR_ITER') or opname.startswith('UNARY_'):
            key = (opname, type(ctf.get_tos_value()))
        elif opname == 'BINARY_SUBSCR':
            key = (opname, type(ctf.get_tos_value(0)), type(ctf.get_tos_value(1)))
        elif opname == 'COMPARE_OP':
            key = (opname, i.argval)
        else:
            key = i.opname
        self.counts[key] += 1
        if (OPCODE_COUNT+1) % 10000 == 0:
            self.dump()

    def dump(self):
        print('===')
        for code, count in self.leaf_calls.most_common(10):
            print('-- call count: {:8} bytecodes: {:5} code: {}'.format(count, len(tuple(dis.get_instructions(code))), code))
            #dis.dis(code)

        pprint.pprint(self.counts.most_common(20))


#TRACE_DUMPER = bytecode_trace.FakeTraceDumper()
TRACE_DUMPER = CountingTraceDumper()


# pytype: disable=base-class-error
class _PyTryBlock(ctypes.Structure):
    _fields_ = [
        ('b_type', ctypes.c_uint),
        ('b_handler', ctypes.c_uint),
        ('b_level', ctypes.c_uint),
    ]
# pytype: enable=base-class-error


eprint = functools.partial(print, file=sys.stderr)
cprint = functools.partial(termcolor.cprint, file=sys.stderr)
#def print(*args, **kwargs): pass
#def cprint(*args, **kwargs): pass


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
            'f_locals': 7,  # "Local symbol table".
            'f_valuestack': 8,
            'f_stacktop': 9,
            'f_localsplus': 45,
        },
    }
    ULONG_SIZE_IN_BYTES = 8
    UINT_SIZE_IN_BYTES = 4
    PTR_TO_LONG = ctypes.POINTER(ctypes.c_ulong)

    def __init__(self, frame: types.FrameType):
        self.frame_id = id(frame)
        self.frame_ptr = ctypes.cast(id(frame),
                                     self.PTR_TO_LONG)
        self.offsets = self.VERSION_TO_CTYPE_ULONG_OFFSETS[
            sys.version_info[:2]]
        for offset in range(30):
            if id(frame.f_back) == self.frame_ptr[offset]:
                self.f_back_offset = offset

    @classmethod
    def _id2obj(cls, id_: int) -> Any:
        """Mutates a tuple cell to point at a new location."""
        t = (None,)
        try:
            ctypes.cast(id(t), cls.PTR_TO_LONG)[3] = id_
            return t[0]
        finally:
            # Do we need to do this to keep the refcounts sane?
            ctypes.cast(id(t), cls.PTR_TO_LONG)[3] = id(None)

    def get_value_stack(self):
        """Returns the contents of the f_valuestack slot in the PyFrameObject.

        In C the type of the returned value is ``PyObject**``.
        """
        return self.frame_ptr[self.offsets['f_valuestack']]

    def get_value_stack_as_ptr(self):
        return ctypes.cast(self.get_value_stack(),
                           self.PTR_TO_LONG)

    def get_localsplus_start(self):
        """Returns a pointer to the "localsplus" region of the PyFrameObject.

        This is the start of a variable sized region.

        In C the type of the returned value is ``PyObject**``.
        """
        return (self.frame_id +
                self.offsets['f_localsplus'] * self.ULONG_SIZE_IN_BYTES)

    def get_localsplus_start_as_ptr(self):
        return ctypes.cast(self.get_localsplus_start(),
                           self.PTR_TO_LONG)

    def get_stack_top(self):
        """Returns a pointer to the next free slot in the value stack.

        In C the type of the returned value is ``PyObject**``.
        """
        return self.frame_ptr[self.offsets['f_stacktop']]

    def print_block_stack(self):
        assert sys.version_info[:2] == (3, 7)
        f_iblock = ctypes.cast(
            self.frame_id,
            ctypes.POINTER(ctypes.c_uint))[112//self.UINT_SIZE_IN_BYTES]
        eprint('f_iblock:', f_iblock)

        type_to_str = {
            257: 'EXCEPT_HANDLER',
            120: 'SETUP_LOOP',
            121: 'SETUP_EXCEPT',
            122: 'SETUP_FINALLY',
        }

        f_blockstack = ctypes.cast(self.frame_id+120,
                                   ctypes.POINTER(_PyTryBlock))
        block_stack = []
        for i in range(f_iblock):
            ptb = f_blockstack[i]
            type_str = type_to_str[ptb.b_type]
            handler = -1 if ptb.b_handler == 0xffffffff else ptb.b_handler
            eprint(' blockstack %d: type: %s handler: %s level: %d' % (
                    i, type_str, handler, ptb.b_level))
            block_stack.append(bytecode_trace.BlockStackEntry(
                type_str, handler, ptb.b_level))

        TRACE_DUMPER.note_block_stack(block_stack)

    def get_tos_value(self, i=0):
        value = self.get_value_stack_as_ptr()[i]
        if value == 0:
            return None
        return self._id2obj(value)

    def print_stack(self):
        # Left in, just in case there's some need to look at the pointer
        # values.
        #
        # print(' frame start   (frameobj*):', hex(self.frame_id))
        # print(' localplus start (pyobj**):',
        #       hex(self.get_localsplus_start()))
        # print(' value stack     (pyobj**):', hex(self.get_value_stack()))
        # print(' stack top       (pyobj**):', hex(self.get_stack_top()))

        count = self.get_stack_top() - self.get_value_stack()
        assert count % self.ULONG_SIZE_IN_BYTES == 0
        stack_items = count // self.ULONG_SIZE_IN_BYTES

        localsplus_items = (
            (self.get_stack_top() - self.get_localsplus_start()) //
            self.ULONG_SIZE_IN_BYTES)
        eprint(' localsplus_items sans stack:', localsplus_items-stack_items)
        for i in range(localsplus_items-stack_items):
            localsplus_ptr = self.get_localsplus_start_as_ptr()
            value = localsplus_ptr[i]
            if value == 0:
                cprint('  LP{}: <null>'.format(i), file=sys.stderr,
                       color='red')
            else:
                obj = self._id2obj(value)
                cprint('  LP{}: {!r} :: {!r}'.format(i, type(obj), obj),
                       file=sys.stderr, color='red')

        eprint(' stack (%d):' % stack_items)
        for i in range(stack_items):
            stack_value = self.get_value_stack_as_ptr()[i]
            if stack_value == 0:
                eprint('  TOS%d: <null>' % i)
            else:
                obj = self._id2obj(stack_value)
                eprint('  TOS%d: %r ::' % (i, type(obj)), repr(obj), '::', id(obj))
                if isinstance(obj, types.CodeType):
                    eprint('    co_varnames: {!r}'.format(obj.co_varnames))
                    eprint('    co_cellvars: {!r}'.format(obj.co_cellvars))
                if isinstance(obj, types.FunctionType):
                    eprint('    closure:     {!r}'.format(obj.__closure__))
                    eprint('    co_cellvars: {!r}'.format(
                            obj.__code__.co_cellvars))
                    eprint('    co_freevars: {!r}'.format(
                            obj.__code__.co_freevars))
        self.print_block_stack()


def _note_opcode_event(frame, opcodeno, verbose=True) -> None:
    # From the docs:
    #     The interpreter is about to execute a new opcode (see dis for
    #     opcode details). The local trace function is called; arg is None;
    #     the return value specifies the new local trace function.
    #     Per-opcode events are not emitted by default: they must be
    #     explicitly requested by setting f_trace_opcodes to True on the
    #     frame.
    # -- https://docs.python.org/3/library/sys.html#sys.settrace
    if verbose:
        eprint('opcode about to execute...')

    ctf = CtypeFrame(frame)
    instructions = dis.get_instructions(frame.f_code)
    instruction = next(inst for inst in instructions
                       if inst.offset == frame.f_lasti)
    TRACE_DUMPER.note_instruction(instruction, ctf)

    if verbose:
        eprint(' frame.f_lasti:', frame.f_lasti)
        cprint('i: {} code: {}; lineno: {}'.format(opcodeno, frame.f_code, frame.f_lineno),
               color='blue')
        cprint(' instruction: {}'.format(instruction), color='yellow')
        locals_ = dict(frame.f_locals)
        for name in ['__builtins__']:
            if name in locals_:
                del locals_[name]
        eprint(' frame.f_locals:', locals_)
        try:
            eprint(' stack effect:', dis.stack_effect(instruction.opcode,
                  instruction.arg))
        except ValueError:
            pass
        ctf.print_stack()


def note_trace(frame, event, arg):
    global OPCODE_COUNT
    #eprint('--- trace')

    def print_frame_info():
        eprint(' frame.f_lasti:', frame.f_lasti)
        eprint(' frame.f_lineno:', frame.f_lineno)
        # eprint(' frame.f_locals:', frame.f_locals)

    if event == 'call':
        TRACE_DUMPER.note_call(frame.f_code)
        filename = frame.f_code.co_filename
        #eprint('CALLING:', filename)
        # Turn on opcode tracing for the frame we're entering.
        if not filename.startswith('<frozen'):
            frame.f_trace_opcodes = True
    elif event == 'opcode':
        _note_opcode_event(frame, OPCODE_COUNT)
        OPCODE_COUNT += 1
        pass
    elif event == 'line':
        #eprint('line!')
        #print_frame_info()
        pass
    elif event == 'return':
        TRACE_DUMPER.note_return(frame.f_code)
        pass
    elif event == 'exception':
        pass
    else:
        eprint('unhandled event:', event)
        sys.exit(-1)

    return note_trace


def main():
    global TRACE_DUMPER
    parser = optparse.OptionParser()
    parser.add_option('--dump_trace', help='Path to dump bytecode trace to.')
    opts, args = parser.parse_args()

    if opts.dump_trace:
        TRACE_DUMPER = bytecode_trace.BytecodeTraceDumper(opts.dump_trace)

    path = args[0]

    sys.argv = args[1:]

    print('Reading path:', path, file=sys.stderr)
    with open(path) as f:
        contents = f.read()

    sys.settrace(note_trace)
    globals_ = {'__name__': '__main__'}
    exec(contents, globals_)
    sys.settrace(None)

    print('opcode count:', OPCODE_COUNT)

    if opts.dump_trace:
        print('Dumping', len(TRACE_DUMPER.entries), 'trace entries...')

    TRACE_DUMPER.dump()


if __name__ == '__main__':
    main()
