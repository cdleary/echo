import ctypes
from typing import Callable

from echo.cg.common import *
from echo.cg.masm import Masm, Register, Scale


def make_get_ob_size() -> Callable:
    masm = (Masm()
            .movq_mr(PYVAR_OFFSET_OB_SIZE, Register.RDI, Register.RAX)
            .ret())
    get_ob_size = masm.to_callable((ctypes.c_void_p,), ctypes.c_uint64)
    return get_ob_size


def make_get_ob_digit() -> Callable[[int, int], int]:
    masm = (Masm()
            .movl_mr_bisd(offset=PYVAR_OFFSET_OB_DIGIT, base=Register.RDI,
                          index=Register.RSI, scale=Scale.SCALE_4,
                          dst=Register.RAX)
            .ret())
    get_ob_digit = masm.to_callable((ctypes.c_void_p, ctypes.c_uint64),
                                    ctypes.c_uint32)
    return get_ob_digit


def make_long_eq() -> Callable[[int, int], bool]:
    masm = (Masm()
            .movq_mr(PYVAR_OFFSET_OB_SIZE, Register.RDI, Register.RAX)
            .movq_mr(PYVAR_OFFSET_OB_SIZE, Register.RSI, Register.RDX)
            .cmpq_rr(Register.RAX, Register.RDX)
            .jne('not_equal')
            .decq(Register.RAX)
            .label('each_digit')
            .movl_mr_bisd(offset=PYVAR_OFFSET_OB_DIGIT, base=Register.RDI,
                          index=Register.RAX, scale=Scale.SCALE_4,
                          dst=Register.RDX)
            .movl_mr_bisd(offset=PYVAR_OFFSET_OB_DIGIT, base=Register.RSI,
                          index=Register.RAX, scale=Scale.SCALE_4,
                          dst=Register.RCX)
            .cmpq_rr(Register.RCX, Register.RDX)
            .jne('not_equal')
            .decq(Register.RAX)
            .jns('each_digit')
            .movl_ir(1, Register.RAX)
            .ret()
            .label('not_equal')
            .xorl_rr(Register.RAX, Register.RAX)
            .ret())
    get_long_eq = masm.to_callable((ctypes.c_void_p, ctypes.c_void_p),
                                   ctypes.c_bool)
    return get_long_eq


def make_long_add() -> Callable[[int, int], int]:
    libpython = ctypes.CDLL('libpython3.7m.so')
    addr = ctypes.cast(libpython.PyNumber_Add, ctypes.c_void_p).value
    print('addr:', hex(addr))
    masm = (Masm()
            .movq_i64r(addr, Register.RAX)
            .callq_r(Register.RAX)
            .ret())
    long_add = masm.to_callable((ctypes.c_void_p, ctypes.c_void_p),
                                ctypes.py_object)
    return long_add
