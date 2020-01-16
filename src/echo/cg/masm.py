"""Derived from SpiderMonkey's macroassembler."""

import enum
from typing import Union

from echo.elog import log


class OneByteOpcode(enum.Enum):
    PRE_REX = 0x40
    PRE_OPERAND_SIZE = 0x66
    OP_GROUP1_EvIz = 0x81
    OP_GROUP1_EvIb = 0x83
    OP_MOV_EAXIv = 0xb8
    OP_MOV_EvGv = 0x89
    OP_MOV_GvEv = 0x8b


class GroupOpcode(enum.Enum):
    GROUP1_OP_ADD = 0
    GROUP1_OP_OR = 1


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
    assert x & 0xffffffff == x, hex(x)
    if x & 0x7f == x:
        return True
    raise NotImplementedError(x)


class Masm:
    def __init__(self):
        self._bytes = []

    def put_byte(self, x: int) -> None:
        assert x & 0xff == x
        self._bytes.append(x)

    def immediate8(self, imm: int) -> None:
        assert imm & 0xff == imm
        self.put_byte(imm)

    def put_int(self, imm: int) -> None:
        assert imm & 0xffffffff == imm, imm
        self.put_byte(imm & 0xff)
        self.put_byte((imm >> 8) & 0xff)
        self.put_byte((imm >> 16) & 0xff)
        self.put_byte((imm >> 24) & 0xff)

    def immediate32(self, imm: int) -> None:
        self.put_int(imm)

    def put_mod_rm(self, mode: ModRmMode, reg: int, rm: Register):
        assert isinstance(reg, int), reg
        self.put_byte((mode.value << 6) | ((reg & 7) << 3) | (rm.value & 7))

    def register_mod_rm(self, reg: int, rm: Register):
        self.put_mod_rm(ModRmMode.Register, reg, rm)

    def memory_mod_rm(self, reg: int, base: Register, offset: int) -> None:
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

    def emit_rex_if(self, condition: bool, r: int, x: int, b: int) -> None:
        if (condition or reg_requires_rex(r) or reg_requires_rex(x)
                or reg_requires_rex(b)):
            self.emit_rex(False, r, x, b)

    def emit_rex_if_needed(self, r: int, x: int, b: int) -> None:
        self.emit_rex_if(reg_requires_rex(r) or reg_requires_rex(x) or
                         reg_requires_rex(b), r, x, b)

    def prefix(self, opcode: OneByteOpcode) -> None:
        self.put_byte(opcode.value)

    def one_byte_op(self, opcode: OneByteOpcode, group_opcode: GroupOpcode,
                    rm: Register) -> None:
        self.emit_rex_if_needed(group_opcode.value, 0, rm.value)
        self.put_byte(opcode.value)
        self.register_mod_rm(group_opcode.value, rm)

    def one_byte_op_or(self, opcode: OneByteOpcode,
                       reg: Register) -> None:
        self.emit_rex_if_needed(0, 0, reg.value)
        self.put_byte(opcode.value + (reg.value & 7))

    def one_byte_op_orri(self, opcode: OneByteOpcode,
                         reg: Register, base: Register,
                         offset: int) -> None:
        self.emit_rex_if_needed(reg.value, 0, base.value)
        self.put_byte(opcode.value)
        self.memory_mod_rm(reg.value, base, offset)

    def _one_byte_ir(self, group: GroupOpcode, imm: int,
                     dst: Register) -> None:
        if can_sign_extend_8_32(imm):
            self.one_byte_op(OneByteOpcode.OP_GROUP1_EvIb, group, dst)
            self.immediate8(imm)
        else:
            self.one_byte_op(OneByteOpcode.OP_GROUP1_EvIz, group, dst)
            self.immediate32(imm)

    def addl_ir(self, imm: int, dst: Register):
        self._one_byte_ir(GroupOpcode.GROUP1_OP_ADD, imm, dst)

    def orl_ir(self, imm: int, dst: Register):
        self._one_byte_ir(GroupOpcode.GROUP1_OP_OR, imm, dst)

    def movl_ir(self, imm: int, dst: Register):
        self.one_byte_op_or(OneByteOpcode.OP_MOV_EAXIv, dst)
        self.immediate32(imm)

    def movw_rm(self, src: Register, offset: int, base: Register) -> None:
        self.prefix(OneByteOpcode.PRE_OPERAND_SIZE)
        self.one_byte_op_orri(OneByteOpcode.OP_MOV_EvGv, src, base, offset)

    def movl_mr(self, offset: int, base: Register, dst: Register) -> None:
        self.one_byte_op_orri(OneByteOpcode.OP_MOV_GvEv, dst, base, offset)
