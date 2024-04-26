from typing import Callable

import dis
import os
import types
import sys
import functools


EachInstFun = Callable[[dis.Instruction, types.FrameType], None]


def _note_trace(frame: types.FrameType, event, arg, each_inst: EachInstFun):
    filename = frame.f_code.co_filename
    if filename.startswith('<frozen'):
        return functools.partial(_note_trace, each_inst=each_inst)

    frame.f_trace_opcodes = True
    frame.f_trace = _note_trace
    # print(repr(event), frame)
    if event == 'call':
        # print(repr(event), frame)
        pass
    elif event == 'opcode':
        instructions = dis.get_instructions(frame.f_code)
        instruction = next(inst for inst in instructions
                           if inst.offset == frame.f_lasti)
        each_inst(instruction, frame)
        if instruction.opname == 'EXTENDED_ARG':
            # For some reason the opcode after the extended arg doesn't seem
            # to get traced.
            instruction2 = next(inst for inst in instructions
                                if inst.offset > frame.f_lasti)
            each_inst(instruction2, frame)
    elif event == 'return':
        # print('=>', repr(arg), repr(type(arg)))
        pass
    else:
        pass
    return functools.partial(_note_trace, each_inst=each_inst)


def trace_path(path: str, each_inst: EachInstFun) -> None:
    with open(path) as f:
        contents = f.read()
    globals_ = {'__name__': '__main__', '__file__': os.path.realpath(path)}
    # del sys.modules['enum']
    # del sys.modules['re']
    # del sys.modules['sre_compile']
    # del sys.modules['sre_parse']
    # del sys.modules['sre_constants']
    # del sys.modules['types']
    # sys.modules.pop('collections')
    f = sys._getframe(0)
    code = compile(contents, os.path.realpath(path), 'exec')
    note_trace = functools.partial(_note_trace, each_inst=each_inst)
    sys.settrace(note_trace)
    try:
        exec(code, globals_)
    finally:
        sys.settrace(None)
