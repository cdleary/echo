import enum

from echo.elog import log


class OneByteOpcode(enum.Enum):
    PRE_REX = 0x40
    OP_GROUP1_EvIz = 0x81
    OP_GROUP1_EvIb = 0x83


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


def reg_requires_rex(r: int) -> bool:
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

    def immediate32(self, imm: int) -> None:
        raise NotImplementedError

    def put_mod_rm(self, mode: ModRmMode, reg: int, rm: Register):
        self.put_byte((mode.value << 6) | ((reg & 7) << 3) | (rm.value & 7))

    def register_mod_rm(self, reg: int, rm: Register):
        self.put_mod_rm(ModRmMode.Register, reg, rm)

    def emit_rex(self, w: bool, r: int, x: int, b: int) -> None:
        self.put_byte(OneByteOpcode.PRE_REX.value |
                      (int(w) << 3) | ((r >> 3) << 3) |
                      ((x >> 3) << 1) | (b >> 3))

    def emit_rex_if(self, condition: bool, r: int, x: int, b: int) -> None:
        if (condition or reg_requires_rex(r) or reg_requires_rex(x)
                or reg_requires_rex(b)):
            self.emit_rex(False, r, x, b)

    def emit_rex_if_needed(self, r: int, x: int, b: int) -> None:
        self.emit_rex_if(reg_requires_rex(r) or reg_requires_rex(x) or
                         reg_requires_rex(b), r, x, b)

    def one_byte_op(self, opcode: OneByteOpcode, group_opcode: GroupOpcode,
                    rm: Register) -> None:
        self.emit_rex_if_needed(group_opcode.value, 0, rm.value)
        self.put_byte(opcode.value)
        self.register_mod_rm(group_opcode.value, rm)

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
        log('masm', 'orl ${:#x}, {name_ireg(4, dst)}')
        self._one_byte_ir(GroupOpcode.GROUP1_OP_OR, imm, dst)
