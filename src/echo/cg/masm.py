"""Derived from SpiderMonkey's macroassembler.

A vision:

    @masm
    def py_hashpointer(p: quad) -> quad:
        y = p
        y = (y >> 4) | (y << 8 * sizeof(quad) - 4)
        x = y
        return (x == -1).select(quad(-2), x)
"""


import ctypes
import enum
import errno
import math
import mmap
import os
from typing import Union, Any, Tuple, Type, Callable

from echo.elog import log


class OneByteOpcode(enum.Enum):
    PRE_REX = 0x40
    PRE_OPERAND_SIZE = 0x66
    OP_GROUP1_EvIz = 0x81
    OP_GROUP1_EvIb = 0x83
    OP_GROUP2_EvIb = 0xc1
    OP_GROUP2_Ev1 = 0xd1
    OP_MOV_EAXIv = 0xb8
    OP_MOV_EvGv = 0x89
    OP_MOV_GvEv = 0x8b
    OP_ADD_EvGv = 0x01
    OP_TEST_EvGv = 0x85
    OP_OR_EvGv = 0x09
    OP_CMP_EvGv = 0x39
    OP_CMP_GvEv = 0x3b
    OP_GROUP11_EvIz = 0xc7
    OP_2BYTE_ESCAPE = 0x0f
    OP_RET = 0xc3
    OP_INT3 = 0xcc


class TwoByteOpcode(enum.Enum):
    OP_CMOVZ_GvEv = 0x44


class GroupOpcode(enum.Enum):
    GROUP1_OP_ADD = 0
    GROUP1_OP_OR = 1
    GROUP1_OP_CMP = 7
    GROUP2_OP_SHL = 4
    GROUP2_OP_SHR = 5
    GROUP2_OP_SAR = 7
    GROUP11_MOV = 0


class Register(enum.Enum):
    RAX = 0
    RCX = 1
    RDX = 2
    RBX = 3
    RSP = 4
    RBP = 5
    RSI = 6
    RDI = 7
    R8 = 8
    R9 = 9
    R10 = 10
    R11 = 11
    R12 = 12
    R13 = 13
    R14 = 14
    R15 = 15


HAS_SIB = Register.RSP
HAS_SIB2 = Register.R12
NO_BASE = Register.RBP
NO_BASE2 = Register.R13
PAGE_SIZE = os.sysconf('SC_PAGE_SIZE')


def reg_requires_rex(r: Union[int, Register]) -> bool:
    if isinstance(r, Register):
        r = r.value
    return r >= Register.R8.value


class ModRmMode(enum.Enum):
    MemoryNoDisp = 0
    MemoryDisp8 = 1
    MemoryDisp32 = 2
    Register = 3


def can_sign_extend_8_32(x: int):
    x = ctypes.c_uint32(x).value
    assert x & 0xffffffff == x, hex(x)
    def neg(x): return ctypes.c_uint32(-x).value
    if x & 0x7f == x:
        return True
    if (x >> 31) and (neg(x) & 0x7f) == neg(x):
        return True
    raise NotImplementedError(x)


class MappedCode:
    def __init__(self, buf: ctypes.Array, libc: ctypes.CDLL):
        self.buf = buf
        self.libc = libc

    def __del__(self):
        length = len(self.buf)
        assert length > 0
        assert length % PAGE_SIZE == 0
        retval = self.libc.munmap(self.buf, length)
        if retval == 0:
            return
        code = errno.errorcode[ctypes.get_errno()]
        msg = (f'Could not unmap buffer: {self.buf} length: {length} '
               f'errno: {code}')
        raise OSError(msg)


class Masm:
    def __init__(self):
        self._bytes = []

    def to_callable(self, arg_types: Tuple[Type, ...],
                    restype: Type) -> Callable:
        f_type = ctypes.CFUNCTYPE(restype, *arg_types)
        ptr = self.to_code()
        casted = ctypes.cast(ptr.buf, f_type)

        def masm_call(*args):
            return restype(casted(*args)).value

        masm_call.masm_code = ptr

        return masm_call

    def to_code(self) -> MappedCode:
        libc = ctypes.CDLL('libc.so.6', use_errno=True)
        pages = length = int(math.ceil(len(self._bytes) / PAGE_SIZE))
        assert pages > 0, pages
        libc_mmap = libc.mmap
        libc_mmap.restype = ctypes.c_void_p
        mapped_int = libc_mmap(
            0, pages * PAGE_SIZE, mmap.PROT_WRITE | mmap.PROT_READ,
            mmap.MAP_ANONYMOUS | mmap.MAP_PRIVATE, 0, 0)
        mapped = ctypes.c_void_p(mapped_int)

        if mapped.value == ctypes.c_void_p(-1).value:
            raise OSError('Could not make JIT code mapping: ' +
                          errno.errorcode[ctypes.get_errno()])
        length = pages * PAGE_SIZE
        buffer_t = eval('ctypes.c_byte * length')
        buf = buffer_t.from_address(mapped_int)

        log('masm:to_code', f'mapped: {mapped_int:#x}')

        # "memcpy" into the mmaped buffer.
        for i, b in enumerate(self._bytes):
            buf[i] = b

        retval = libc.mprotect(mapped, length, mmap.PROT_EXEC | mmap.PROT_READ)
        if retval != 0:
            msg = ('Could not turn JIT code executable: ' +
                   errno.errorcode[ctypes.get_errno()])
            libc.munmap(mapped, length)
            raise OSError(msg)
        return MappedCode(buf, libc)

    def put_byte(self, x: int) -> None:
        assert x & 0xff == x
        self._bytes.append(x)

    def immediate8(self, imm: int) -> 'Masm':
        assert can_sign_extend_8_32(imm), imm
        self.put_byte(imm & 0xff)
        return self

    def put_int(self, imm: int) -> 'Masm':
        imm = ctypes.c_uint32(imm).value
        assert imm & 0xffffffff == imm, imm
        self.put_byte(imm & 0xff)
        self.put_byte((imm >> 8) & 0xff)
        self.put_byte((imm >> 16) & 0xff)
        self.put_byte((imm >> 24) & 0xff)
        return self

    def put_int64(self, imm: int) -> 'Masm':
        imm = ctypes.c_uint64(imm).value
        assert imm & 0xffffffff_ffffffff == imm, imm
        self.put_byte(imm & 0xff)
        self.put_byte((imm >> 8) & 0xff)
        self.put_byte((imm >> 16) & 0xff)
        self.put_byte((imm >> 24) & 0xff)
        self.put_byte((imm >> 32) & 0xff)
        self.put_byte((imm >> 40) & 0xff)
        self.put_byte((imm >> 48) & 0xff)
        self.put_byte((imm >> 56) & 0xff)
        return self

    def immediate32(self, imm: int) -> 'Masm':
        return self.put_int(imm)

    def immediate64(self, imm: int) -> 'Masm':
        return self.put_int64(imm)

    def put_mod_rm(self, mode: ModRmMode, reg: int, rm: Register):
        assert isinstance(reg, int), reg
        self.put_byte((mode.value << 6) | ((reg & 7) << 3) | (rm.value & 7))

    def register_mod_rm(self, reg: Union[int, Register], rm: Register):
        if isinstance(reg, Register):
            reg = reg.value
        self.put_mod_rm(ModRmMode.Register, reg, rm)

    def memory_mod_rm(self, reg: Union[Register, int], base: Register,
                      offset: int) -> None:
        if isinstance(reg, Register):
            reg = reg.value
        assert isinstance(reg, int), reg
        if base == HAS_SIB or base == HAS_SIB2:
            raise NotImplementedError
        else:
            if not offset and base not in (NO_BASE, NO_BASE2):
                self.put_mod_rm(ModRmMode.MemoryNoDisp, reg, base)
            elif can_sign_extend_8_32(offset):
                self.put_mod_rm(ModRmMode.MemoryDisp8, reg, base)
                self.put_byte(offset)
            else:
                self.put_mod_rm(ModRmMode.MemoryDisp32, reg, base)
                self.put_int(offset)

    def emit_rex(self, w: bool, r: int, x: int, b: int) -> None:
        assert isinstance(r, int), r
        assert isinstance(x, int), x
        assert isinstance(b, int), b
        self.put_byte(OneByteOpcode.PRE_REX.value |
                      (int(w) << 3) | ((r >> 3) << 2) |
                      ((x >> 3) << 1) | (b >> 3))

    def emit_rex_w(self, r: int, x: int, b: int) -> None:
        self.emit_rex(True, r, x, b)

    def emit_rex_if(self, condition: bool, r: int, x: int, b: int) -> None:
        if (condition or reg_requires_rex(r) or reg_requires_rex(x)
                or reg_requires_rex(b)):
            self.emit_rex(False, r, x, b)

    def emit_rex_if_needed(self, r: int, x: int, b: int) -> None:
        assert isinstance(r, int), r
        assert isinstance(x, int), x
        assert isinstance(b, int), b
        self.emit_rex_if(reg_requires_rex(r) or reg_requires_rex(x) or
                         reg_requires_rex(b), r, x, b)

    def prefix(self, opcode: OneByteOpcode) -> None:
        self.put_byte(opcode.value)

    def one_byte_op(self, opcode: OneByteOpcode) -> None:
        self.put_byte(opcode.value)

    def two_byte_op(self, opcode: TwoByteOpcode) -> None:
        self.put_byte(OneByteOpcode.OP_2BYTE_ESCAPE.value)
        self.put_byte(opcode.value)

    def two_byte_op_orr(self, opcode: TwoByteOpcode, reg: Union[Register, int],
                        rm: Register) -> 'Masm':
        if isinstance(reg, Register):
            reg = reg.value
        self.emit_rex_if_needed(reg, 0, rm.value)
        self.two_byte_op(opcode)
        self.register_mod_rm(reg, rm)
        return self

    def two_byte_op64_orr(self, opcode: TwoByteOpcode,
                          reg: Union[Register, int], rm: Register) -> 'Masm':
        if isinstance(reg, Register):
            reg = reg.value
        self.emit_rex_w(reg, 0, rm.value)
        self.two_byte_op(opcode)
        self.register_mod_rm(reg, rm)
        return self

    def one_byte_op_ogr(self, opcode: OneByteOpcode, group_opcode: GroupOpcode,
                        rm: Register) -> None:
        self.emit_rex_if_needed(group_opcode.value, 0, rm.value)
        self.put_byte(opcode.value)
        self.register_mod_rm(group_opcode.value, rm)

    def one_byte_op_or(self, opcode: OneByteOpcode,
                       reg: Register) -> 'Masm':
        self.emit_rex_if_needed(0, 0, reg.value)
        self.put_byte(opcode.value + (reg.value & 7))
        return self

    def one_byte_op_orr(self, opcode: OneByteOpcode, reg: Register,
                        rm: Register) -> 'Masm':
        self.emit_rex_if_needed(reg.value, 0, rm.value)
        self.put_byte(opcode.value)
        self.register_mod_rm(reg, rm)
        return self

    def one_byte_op_orri(self, opcode: OneByteOpcode,
                         reg: Register, base: Register,
                         offset: int) -> 'Masm':
        self.emit_rex_if_needed(reg.value, 0, base.value)
        self.put_byte(opcode.value)
        self.memory_mod_rm(reg.value, base, offset)
        return self

    def one_byte_op_64_orri(self, opcode: OneByteOpcode,
                            reg: Register, base: Register,
                            offset: int) -> None:
        self.emit_rex_w(reg.value, 0, base.value)
        self.put_byte(opcode.value)
        self.memory_mod_rm(reg, base, offset)

    def _one_byte_ir(self, group: GroupOpcode, imm: int,
                     dst: Register) -> None:
        if can_sign_extend_8_32(imm):
            self.one_byte_op_ogr(OneByteOpcode.OP_GROUP1_EvIb, group, dst)
            self.immediate8(imm)
        else:
            self.one_byte_op_ogr(OneByteOpcode.OP_GROUP1_EvIz, group, dst)
            self.immediate32(imm)

    def one_byte_op_64_or(self, opcode: OneByteOpcode,
                          reg: Register) -> 'Masm':
        self.emit_rex_w(0, 0, reg.value)
        self.put_byte(opcode.value + (reg.value & 7))
        return self

    def one_byte_op_64_orr(self, opcode: OneByteOpcode, reg: Register,
                           rm: Register) -> 'Masm':
        self.emit_rex_w(reg.value, 0, rm.value)
        self.put_byte(opcode.value)
        self.register_mod_rm(reg, rm)
        return self

    def one_byte_op_64_ogr(self, opcode: OneByteOpcode, group: GroupOpcode,
                           rm: Register) -> 'Masm':
        self.emit_rex_w(group.value, 0, rm.value)
        self.put_byte(opcode.value)
        self.register_mod_rm(group.value, rm)
        return self

    def addl_ir(self, imm: int, dst: Register) -> 'Masm':
        self._one_byte_ir(GroupOpcode.GROUP1_OP_ADD, imm, dst)
        return self

    def addl_rr(self, src: Register, dst: Register) -> 'Masm':
        self.one_byte_op_orr(OneByteOpcode.OP_ADD_EvGv, src, dst)
        return self

    def addq_rr(self, src: Register, dst: Register) -> 'Masm':
        return self.one_byte_op_64_orr(OneByteOpcode.OP_ADD_EvGv, src, dst)

    def orl_ir(self, imm: int, dst: Register) -> 'Masm':
        self._one_byte_ir(GroupOpcode.GROUP1_OP_OR, imm, dst)
        return self

    def movl_ir(self, imm: int, dst: Register) -> 'Masm':
        self.one_byte_op_or(OneByteOpcode.OP_MOV_EAXIv, dst)
        self.immediate32(imm)
        return self

    def movl_rr(self, src: Register, dst: Register) -> 'Masm':
        self.one_byte_op_orr(OneByteOpcode.OP_MOV_EvGv, src, dst)
        return self

    def movq_rr(self, src: Register, dst: Register) -> 'Masm':
        return self.one_byte_op_64_orr(OneByteOpcode.OP_MOV_EvGv, src, dst)

    def movq_i32r(self, imm: int, dst: Register) -> 'Masm':
        """
        Note: the immediate is sign extended to 64 bits before being placed in
        the dst register.
        """
        return (self
                .one_byte_op_64_ogr(OneByteOpcode.OP_GROUP11_EvIz,
                                    GroupOpcode.GROUP11_MOV, dst)
                .immediate32(imm))

    def movq_i64r(self, imm: int, dst: Register) -> 'Masm':
        return (self
                .one_byte_op_64_or(OneByteOpcode.OP_MOV_EAXIv, dst)
                .immediate64(imm))

    def orq_rr(self, src: Register, dst: Register) -> 'Masm':
        return self.one_byte_op_64_orr(OneByteOpcode.OP_OR_EvGv, src, dst)

    def testq_rr(self, src: Register, dst: Register) -> 'Masm':
        return self.one_byte_op_64_orr(OneByteOpcode.OP_TEST_EvGv, src, dst)

    def cmpq_ir(self, imm: int, dst: Register) -> 'Masm':
        if imm == 0:
            return self.testq_rr(dst, dst)

        if can_sign_extend_8_32(imm):
            self.one_byte_op_64_ogr(OneByteOpcode.OP_GROUP1_EvIb,
                                    GroupOpcode.GROUP1_OP_CMP, dst)
            self.immediate8(imm)
        else:
            self.one_byte_op_64_ogr(OneByteOpcode.OP_GROUP1_EvIz,
                                    GroupOpcode.GROUP1_OP_CMP, dst)
            self.immediate32(imm)
        return self

    def movq_mr(self, offset: int, base: Register, dst: Register) -> 'Masm':
        self.one_byte_op_64_orri(OneByteOpcode.OP_MOV_GvEv, dst, base, offset)
        return self

    def movw_rm(self, src: Register, offset: int, base: Register) -> 'Masm':
        self.prefix(OneByteOpcode.PRE_OPERAND_SIZE)
        self.one_byte_op_orri(OneByteOpcode.OP_MOV_EvGv, src, base, offset)
        return self

    def movl_mr(self, offset: int, base: Register, dst: Register) -> 'Masm':
        self.one_byte_op_orri(OneByteOpcode.OP_MOV_GvEv, dst, base, offset)
        return self

    def _shift_i8r(self, group: GroupOpcode, imm: int, dst: Register):
        if imm == 1:
            self.one_byte_op_64_ogr(OneByteOpcode.OP_GROUP2_Ev1,
                                    group, dst)
        else:
            self.one_byte_op_64_ogr(OneByteOpcode.OP_GROUP2_EvIb,
                                    group, dst)
            self.immediate8(imm)
        return self

    def shrq_i8r(self, imm: int, dst: Register) -> 'Masm':
        return self._shift_i8r(GroupOpcode.GROUP2_OP_SHR, imm, dst)

    def shlq_i8r(self, imm: int, dst: Register) -> 'Masm':
        return self._shift_i8r(GroupOpcode.GROUP2_OP_SHL, imm, dst)

    def cmovzq_rr(self, src: Register, dst: Register) -> 'Masm':
        return self.two_byte_op64_orr(TwoByteOpcode.OP_CMOVZ_GvEv, dst, src)

    def int3(self) -> 'Masm':
        self.one_byte_op(OneByteOpcode.OP_INT3)
        return self

    def ret(self) -> 'Masm':
        self.one_byte_op(OneByteOpcode.OP_RET)
        return self
