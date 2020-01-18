import ctypes
import subprocess
import tempfile
from typing import Text

from echo.cg.masm import Masm, Register


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


def test_binary_mnemonics():
    for case in [
        ('shrq_i8r', 0x2, Register.R13, 'shr $0x2,%r13'),
        ('shrq_i8r', 0x1, Register.R13, 'shr %r13'),
        ('shlq_i8r', 0x2, Register.R13, 'shl $0x2,%r13'),
        ('shlq_i8r', 0x1, Register.R13, 'shl %r13'),
        ('cmpq_ir', 0, Register.R13, 'test %r13,%r13'),
        ('cmpq_ir', 0x2, Register.R13, 'cmp $0x2,%r13'),
        ('orq_rr', Register.R14, Register.R13, 'or %r14,%r13'),
        ('cmovzq_rr', Register.R14, Register.R13, 'cmove %r14,%r13'),
        ('cmovzq_rr', Register.RDI, Register.RAX, 'cmove %rdi,%rax'),
        ('movq_i32r', 0xdeadbeef, Register.R14,
         'mov $0xffffffffdeadbeef,%r14'),
        ('movq_i64r', 0xdeadbeefcafef00d, Register.R14,
         'movabs $0xdeadbeefcafef00d,%r14'),
    ]:
        masm = Masm()
        f = getattr(masm, case[0])
        f(case[1], case[2])
        assert disassemble(masm) == case[3]


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

    assert do_call(-1) == ctypes.c_uint64(-2).value
    assert do_call(0xdeadbeefcafef00d) == 0xddeadbeefcafef00


PYDICT_OFFSET_MA_USED = 16  # ssize_t
PYDICT_OFFSET_MA_VERSION_TAG = 24  # uint64_t
PYDICT_OFFSET_MA_KEYS = 32  # PyDictKeysObject*


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
    assert get_size(id(d)) == 0
    vtag0 = get_vtag(id(d))
    d['foo'] = 42
    assert get_size(id(d)) == 1
    vtag1 = get_vtag(id(d))
    assert vtag0 != vtag1
