#!/usr/bin/env python3

import collections
import datetime
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
VERBOSE = True


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


eprint = functools.partial(print, file=sys.stderr)
cprint = functools.partial(termcolor.cprint, file=sys.stderr)
#def print(*args, **kwargs): pass
#def cprint(*args, **kwargs): pass


def _note_opcode_event(frame, opcodeno, verbose=VERBOSE) -> None:
    # From the docs:
    #     The interpreter is about to execute a new opcode (see dis for
    #     opcode details). The local trace function is called; arg is None;
    #     the return value specifies the new local trace function.
    #     Per-opcode events are not emitted by default: they must be
    #     explicitly requested by setting f_trace_opcodes to True on the
    #     frame.
    # -- https://docs.python.org/3/library/sys.html#sys.settrace
    if verbose:
        #eprint('opcode about to execute...')
        pass

    ctf = CtypeFrame(frame)
    instructions = dis.get_instructions(frame.f_code)
    instruction = next(inst for inst in instructions
                       if inst.offset == frame.f_lasti)
    TRACE_DUMPER.note_instruction(instruction, ctf)

    if verbose:
        #eprint(' frame.f_lasti:', frame.f_lasti)
        #cprint('i: {} code: {}; lineno: {}'.format(opcodeno, frame.f_code, frame.f_lineno),
        #       color='blue')
        cprint(' instruction: {}'.format(instruction), color='yellow')
        #locals_ = dict(frame.f_locals)
        #for name in ['__builtins__']:
        #    if name in locals_:
        #        del locals_[name]
        #eprint(' frame.f_locals:', locals_)
        #try:
        #    eprint(' stack effect:', dis.stack_effect(instruction.opcode,
        #          instruction.arg))
        #except ValueError:
        #    pass
        #ctf.print_stack()


def note_trace(frame, event, arg):
    global OPCODE_COUNT
    #eprint('--- trace')

    def print_frame_info():
        eprint('{}:{}'.format(frame.f_code.co_filename, frame.f_lineno))
        # eprint(' frame.f_lasti:', frame.f_lasti)
        # eprint(' frame.f_lineno:', frame.f_lineno)
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
        if OPCODE_COUNT % 98304 == 0:
            eprint('opcodes: {:,}'.format(OPCODE_COUNT))
        pass
    elif event == 'line':
        #eprint('line!')
        pass
    elif event == 'return':
        #print_frame_info()
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

    #sys.argv = args[1:]

    print('Reading path:', path, file=sys.stderr)
    with open(path) as f:
        contents = f.read()

    sys.settrace(note_trace)
    globals_ = {'__name__': '__main__'}
    start = datetime.datetime.now()
    try:
        exec(contents, globals_)
    except BaseException as e:
        eprint(e)
    end = datetime.datetime.now()
    sys.settrace(None)

    eprint('opcode count: {:,}'.format(OPCODE_COUNT))
    eprint('opcodes/s:    {:,.2f}'.format(OPCODE_COUNT / (end-start).total_seconds()))

    if opts.dump_trace:
        print('Dumping', len(TRACE_DUMPER.entries), 'trace entries...')

    TRACE_DUMPER.dump()


if __name__ == '__main__':
    main()
