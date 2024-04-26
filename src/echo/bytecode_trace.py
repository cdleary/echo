import abc
import dis
import pickle
import types

from typing import Text, Optional, List


class Instruction:
    def __init__(self, instruction: dis.Instruction):
        self.opname = instruction.opname
        self.arg = instruction.arg
        self.argval = (None if isinstance(instruction.argval, types.CodeType)
                       else instruction.argval)
        self.argrepr = instruction.argrepr
        self.offset = instruction.offset
        self.starts_line = instruction.starts_line
        self.is_jump_target = instruction.is_jump_target

    def get_opname_str(self) -> Text:
        if self.opname in ('COMPARE_OP', 'LOAD_NAME', 'LOAD_GLOBAL',
                           'IMPORT_NAME'):
            return '{}({})'.format(self.opname, self.argrepr)
        return self.opname


class BlockStackEntry:
    def __init__(self, type_str: Text, handler: int, level: int):
        self.type_str = type_str
        self.handler = handler
        self.level = level

    def __str__(self) -> Text:
        return 't={},h={},l={}'.format(self.type_str, self.handler, self.level)


class BytecodeTraceEntry:

    def __init__(self, instruction: dis.Instruction):
        self.instruction = Instruction(instruction)
        self.block_stack: Optional[List[BlockStackEntry]] = None

    def get_block_stack_str(self) -> Text:
        return '[{}]'.format(', '.join(str(e) for e in self.block_stack or []))


class AbstractTraceDumper(metaclass=abc.ABCMeta):

    def __init__(self) -> None:
        self.entries: List[BytecodeTraceEntry] = []

    @abc.abstractmethod
    def note_instruction(self, instruction: dis.Instruction):
        raise NotImplementedError

    @abc.abstractmethod
    def note_block_stack(self, block_stack: List[BlockStackEntry]):
        raise NotImplementedError

    @abc.abstractmethod
    def dump(self):
        raise NotImplementedError


class FakeTraceDumper(AbstractTraceDumper):
    def note_instruction(self, instruction: dis.Instruction):
        pass

    def note_block_stack(self, block_stack: List[BlockStackEntry]):
        pass

    def dump(self):
        pass


class BytecodeTraceDumper(AbstractTraceDumper):
    def __init__(self, path: Text):
        super().__init__()
        self.path = path

    def note_instruction(self, instruction: dis.Instruction):
        self.entries.append(BytecodeTraceEntry(instruction))
        self.dump()

    def note_block_stack(self, block_stack: List[BlockStackEntry]):
        self.entries[-1].block_stack = block_stack
        self.dump()

    def dump(self):
        with open(self.path, 'wb') as f:
            pickle.dump(self.entries, f)
