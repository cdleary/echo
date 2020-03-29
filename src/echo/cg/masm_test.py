import ctypes
import subprocess
import sys
import tempfile
from typing import Text, Callable

from echo.cg.masm import Masm, Register, Scale, Literal
from echo.cg.longobject import make_get_ob_size, make_get_ob_digit
from echo.cg.common import *

import pytest


def _extract_asm(text: Text) -> Text:

    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('Disassembly of section .data'):
            break

    assembly = []
    lines = lines[i+3:]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            offset, bytes_, mnemonic = line.split('\t')
        except ValueError:
            raise ValueError(text)
        mnemonic = ' '.join(mnemonic.split())
        assembly.append(mnemonic)

    return '\n'.join(assembly)


def disassemble(masm: Masm) -> Text:
    with tempfile.NamedTemporaryFile(suffix='.bin') as f:
        f.write(bytes(masm._bytes))
        f.flush()

        text = subprocess.check_output([
            'objdump', '-mi386', '-Mx86-64', '-bbinary', '-D',
            '--insn-width=20',
            f.name])

    return _extract_asm(text.decode('utf-8'))


def test_addl():
    masm = Masm().addl_ir(0x2, Register.R14)
    assert disassemble(masm) == 'add $0x2,%r14d'


def test_orl():
    masm = Masm().orl_ir(0x2, Register.R14)
    assert disassemble(masm) == 'or $0x2,%r14d'


def test_movl_ir():
    masm = Masm().movl_ir(0x2, Register.R14)
    assert disassemble(masm) == 'mov $0x2,%r14d'


def test_movw_rm():
    masm = Masm().movw_rm(Register.R13, 0x2, Register.R14)
    assert disassemble(masm) == 'mov %r13w,0x2(%r14)'


def test_movl_mr():
    masm = Masm().movl_mr(0x2, Register.R14, Register.R13)
    assert disassemble(masm) == 'mov 0x2(%r14),%r13d'


def test_movq_mr():
    masm = Masm().movq_mr(0x2, Register.R14, Register.R13)
    assert disassemble(masm) == 'mov 0x2(%r14),%r13'


def test_jmp_to_self():
    masm = Masm().label('label').jmp('label')
    masm.perform_relocs()
    assert disassemble(masm) == 'jmp 0x0'


def test_mnemonics():
    for case in [
        ('shrq_i8r', (0x2, Register.R13), 'shr $0x2,%r13'),
        ('shrq_i8r', (0x1, Register.R13), 'shr %r13'),
        ('shlq_i8r', (0x2, Register.R13), 'shl $0x2,%r13'),
        ('shlq_i8r', (0x1, Register.R13), 'shl %r13'),
        ('cmpq_ir', (0, Register.R13), 'test %r13,%r13'),
        ('cmpq_ir', (0x2, Register.R13), 'cmp $0x2,%r13'),
        ('cmpq_rr', (Register.R14, Register.R13), 'cmp %r14,%r13'),
        ('orq_rr', (Register.R14, Register.R13), 'or %r14,%r13'),
        ('xorl_rr', (Register.R14, Register.R13), 'xor %r14d,%r13d'),
        ('cmovzq_rr', (Register.R14, Register.R13), 'cmove %r14,%r13'),
        ('cmovzq_rr', (Register.RDI, Register.RAX), 'cmove %rdi,%rax'),
        ('movq_i32r', (0xdeadbeef, Register.R14),
         'mov $0xffffffffdeadbeef,%r14'),
        ('movq_i64r', (0xdeadbeefcafef00d, Register.R14),
         'movabs $0xdeadbeefcafef00d,%r14'),
        ('sete_r', (Register.RAX,), 'sete %al'),
        ('callq_r', (Register.RAX,), 'callq *%rax'),
        ('callq_r', (Register.R14,), 'callq *%r14'),
        ('xbegin', ('done',), 'xbeginq 0x5'),
        ('xabort_i8', (0xab,), 'xabort $0xab'),
    ]:
        masm = Masm()
        fn, args, target = case
        f = getattr(masm, fn)
        f(*args).label('done')
        assert disassemble(masm) == target


def test_int_double():
    masm = (Masm()
            .movq_rr(Register.RDI, Register.RAX)
            .addq_rr(Register.RAX, Register.RAX)
            .ret())

    i64_to_i64 = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)
    ptr = masm.to_code()
    casted = ctypes.cast(ptr.buf, i64_to_i64)
    assert casted(-1) == -2
    assert casted(1) == 2
    assert casted(2) == 4
    assert casted(17) == 34
    assert casted(int(1 << 32)) == int(2 << 32)


def test_hashpointer():
    masm = (Masm()
            # rax = rdi
            .movq_rr(Register.RDI, Register.RAX)
            # rax >>= 4
            .shrq_i8r(4, Register.RAX)
            # rdi <<= 60
            .shlq_i8r(60, Register.RDI)
            # rax |= rdi
            .orq_rr(Register.RDI, Register.RAX)
            # eflags = (rax == -1)
            .cmpq_ir(-1, Register.RAX)
            # rdi = -2
            .movq_i32r(-2, Register.RDI)
            # rax = cmov.eq -2
            .cmovzq_rr(Register.RDI, Register.RAX)
            .ret())

    do_call = masm.to_callable((ctypes.c_uint64,), ctypes.c_uint64)

    assert do_call(Literal(-1)) == ctypes.c_uint64(-2).value
    assert do_call(Literal(0xdeadbeefcafef00d)) == 0xddeadbeefcafef00


def test_dict_size():
    masm = (Masm()
            .movq_mr(PYDICT_OFFSET_MA_USED, Register.RDI, Register.RAX)
            .ret())
    get_size = masm.to_callable((ctypes.c_void_p,), ctypes.c_uint64)

    masm = (Masm()
            .movq_mr(PYDICT_OFFSET_MA_VERSION_TAG, Register.RDI, Register.RAX)
            .ret())
    get_vtag = masm.to_callable((ctypes.c_void_p,), ctypes.c_uint64)

    d = {}
    assert get_size(d) == 0
    vtag0 = get_vtag(d)
    d[64] = 42
    assert get_size(d) == 1
    vtag1 = get_vtag(d)
    assert vtag0 != vtag1


def test_long_values():
    get_ob_digit = make_get_ob_digit()
    get_ob_size = make_get_ob_size()

    x = 0
    assert get_ob_size(x) == 0
    x = 1
    assert get_ob_size(x) == 1
    assert get_ob_digit(x, Literal(0)) == 1
    x = 2
    assert get_ob_size(x) == 1
    assert get_ob_digit(x, Literal(0)) == 2
    x = 0x0eadbeef
    assert get_ob_size(x) == 1
    assert get_ob_digit(x, Literal(0)) == 0xeadbeef

    x = 1 << 29
    assert get_ob_size(x) == 1
    assert get_ob_digit(x, Literal(0)) == 1 << 29

    x = 0xffff_ffff_ffff_ffff
    assert get_ob_size(x) == 3
    assert get_ob_digit(x, Literal(0)) == 0x3fff_ffff
    assert get_ob_digit(x, Literal(1)) == 0x3fff_ffff
    assert hex(get_ob_digit(x, Literal(2))) == '0xf'


def test_long_two_digits():
    masm = (Masm()
            # rcx = rdi->ob_size  // holds decrementing size
            .movl_mr(PYVAR_OFFSET_OB_SIZE, Register.RDI, Register.RCX)
            # rax = 0  // accumulator
            .xorl_rr(Register.RAX, Register.RAX)
            # .each_digit:
            .label('each_digit')
            # rcx -= 1
            .decq(Register.RCX)
            # rdx = [rdi+offsetof(digits)+rcx<<2]
            .movl_mr_bisd(offset=PYVAR_OFFSET_OB_DIGIT, base=Register.RDI,
                          index=Register.RCX, scale=Scale.SCALE_4,
                          dst=Register.RDX)
            # rax <<= PYLONG_SHIFT
            .shlq_i8r(PYLONG_SHIFT, Register.RAX)
            # rax |= r9
            .orq_rr(Register.RDX, Register.RAX)
            # if (rcx != 0) goto each_digit
            .orq_rr(Register.RCX, Register.RCX)
            .jnz('each_digit')
            .ret())
    pylong_as_ulong = masm.to_callable((ctypes.c_void_p,), ctypes.c_uint64)
    get_ob_size = make_get_ob_size()

    # At 30 bits it rolls over to two digits.
    x = 1 << 30
    assert get_ob_size(x) == 2
    assert pylong_as_ulong(x) == 1 << 30


def test_tsx_basic():
    libc = ctypes.CDLL('libc.so.6')
    libc.malloc.restype = ctypes.c_void_p
    buf = libc.malloc(64)
    print('buf:', hex(buf), file=sys.stderr)

    m = Masm()
    (m
     .movl_ir(0xf00, Register.RAX)
     .movq_rm(Register.RAX, 0, Register.RDI)
     .xbegin('done')
     .movl_ir(0xba5, Register.RAX)
     .movq_rm(Register.RAX, 0, Register.RDI)
     .xabort_i8(0xcd)
     .ret()
     .label('done')
     .nop()
     .ret())

    f = m.to_callable((ctypes.c_void_p,), ctypes.c_uint64)
    assert f(Literal(buf)) == 0xcd << 24 | 1
    assert ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint64))[0] == 0xf00
