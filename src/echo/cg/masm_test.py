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
        offset, bytes_, mnemonic = line.split('\t')
        mnemonic = ' '.join(mnemonic.split())
        assembly.append(mnemonic)

    return '\n'.join(assembly)


def disassemble(masm: Masm) -> Text:
    with tempfile.NamedTemporaryFile(suffix='.bin') as f:
        f.write(bytes(masm._bytes))
        f.flush()

        text = subprocess.check_output([
            'objdump', '-mi386', '-Mx86-64', '-bbinary', '-D', f.name])

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


def test_shrq_i8r():
    masm = Masm().shrq_i8r(0x2, Register.R13)
    assert disassemble(masm) == 'shr $0x2,%r13'

    masm = Masm().shrq_i8r(0x1, Register.R13)
    assert disassemble(masm) == 'shr %r13'


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
