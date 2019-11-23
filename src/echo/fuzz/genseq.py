import enum
from typing import Tuple, Text, Any, Sequence


class StatementKind(enum.Enum):
    ASSIGN = 'assign'
    EXPR = 'expr'


class NameDef:
    def __init__(self, name: Text):
        self.name = name

    def __str__(self) -> Text:
        return self.name


class Statement:
    @classmethod
    def make_assign(cls, ident: NameDef, rhs: 'Expr') -> 'Statement':
        return cls(StatementKind.ASSIGN, (ident, rhs))

    @classmethod
    def make_expr(cls, arg: 'Expr') -> 'Statement':
        return cls(StatementKind.EXPR, (arg,))

    def __init__(self, kind: StatementKind, operands: Tuple[Any, ...]):
        assert isinstance(operands, tuple), operands
        self.kind = kind
        self.operands = operands

    def format(self) -> Text:
        if self.kind == StatementKind.ASSIGN:
            assert len(self.operands) == 2, self.operands
            return '{} = {}'.format(self.operands[0],
                                    self.operands[1].format())
        if self.kind == StatementKind.EXPR:
            assert len(self.operands) == 1, self.operands
            return '{}'.format(self.operands[0].format())
        raise NotImplementedError(self)


class Block:
    def __init__(self, stmts: Sequence[Statement]):
        self.stmts = tuple(stmts)

    def format(self):
        return '\n'.join(s.format() for s in self.stmts)


class ExprKind(enum.Enum):
    INVOKE = 'invoke'
    DICT_LITERAL = 'dict-literal'
    NAME_REF = 'name-ref'


class Expr:
    @classmethod
    def make_dict_literal(cls):
        return cls(ExprKind.DICT_LITERAL, operands=())

    @classmethod
    def make_invoke(cls, lhs: 'Expr', name: Text, *args) -> 'Expr':
        return cls(ExprKind.INVOKE, (lhs, name, *args))

    @classmethod
    def make_name_ref(cls, arg: NameDef) -> 'Expr':
        return cls(ExprKind.NAME_REF, (arg,))

    def __init__(self, kind: ExprKind, operands: Tuple['Expr', ...]):
        assert isinstance(operands, tuple), operands
        self.kind = kind
        self.operands = operands

    def format(self) -> Text:
        if self.kind == ExprKind.DICT_LITERAL:
            assert not self.operands
            return '{}'
        if self.kind == ExprKind.NAME_REF:
            name_def = self.operands[0]
            assert isinstance(name_def, NameDef), name_def
            return '{}'.format(name_def.name)
        if self.kind == ExprKind.INVOKE:
            return '{}.{}({})'.format(
                self.operands[0].format(), self.operands[1],
                ', '.join(o.format() for o in self.operands[2:]))
        raise NotImplementedError(self)
