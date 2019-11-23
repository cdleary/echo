import enum
import textwrap
from typing import Tuple, Text, Any, Sequence


INDENT_PER_LEVEL = 4


class StmtKind(enum.Enum):
    ASSIGN = 'assign'
    EXPR = 'expr'
    CLASS_DEF = 'class-def'
    FN_DEF = 'fn-def'
    RETURN = 'return'
    PASS = 'pass'


class NameDef:
    def __init__(self, name: Text):
        self.name = name

    def format(self) -> Text:
        return self.name

    def __str__(self) -> Text:
        return self.name


class Stmt:
    @classmethod
    def make_return(cls, operand: 'Expr') -> 'Stmt':
        return cls(StmtKind.RETURN, (operand,))

    @classmethod
    def make_pass(cls) -> 'Stmt':
        return cls(StmtKind.PASS, ())

    @classmethod
    def make_class_def(cls, name: NameDef, body: Tuple['Stmt', ...]) -> 'Stmt':
        assert isinstance(body, tuple), body
        return cls(StmtKind.CLASS_DEF, (name, body))

    @classmethod
    def make_fn_def(cls, name: NameDef, args: Tuple[NameDef, ...],
                    body: Tuple['Stmt', ...]) -> 'Stmt':
        return cls(StmtKind.FN_DEF, (name, args, body))

    @classmethod
    def make_assign(cls, ident: NameDef, rhs: 'Expr') -> 'Stmt':
        return cls(StmtKind.ASSIGN, (ident, rhs))

    @classmethod
    def make_expr(cls, arg: 'Expr') -> 'Stmt':
        return cls(StmtKind.EXPR, (arg,))

    def __init__(self, kind: StmtKind, operands: Tuple[Any, ...]):
        assert isinstance(operands, tuple), operands
        self.kind = kind
        self.operands = operands

    def __repr__(self) -> Text:
        return f'{self.__class__.__name__}({self.kind}, {self.operands})'

    def _format(self) -> Text:
        if self.kind == StmtKind.ASSIGN:
            assert len(self.operands) == 2, self.operands
            return '{} = {}'.format(self.operands[0],
                                    self.operands[1].format())
        if self.kind == StmtKind.EXPR:
            assert len(self.operands) == 1, self.operands
            return '{}'.format(self.operands[0].format())
        if self.kind == StmtKind.CLASS_DEF:
            name, body = self.operands
            return ('class {}:\n'.format(name) +
                    '\n'.join(s.format(indent=INDENT_PER_LEVEL) for s in body))
        if self.kind == StmtKind.RETURN:
            return 'return {}'.format(self.operands[0].format())
        if self.kind == StmtKind.PASS:
            return 'pass'
        if self.kind == StmtKind.FN_DEF:
            name, args, body = self.operands
            indent_str = ' ' * INDENT_PER_LEVEL
            body = ('\n' + indent_str).join(s.format() for s in body)
            args_str = ', '.join(a.format() for a in args)
            return f'def {name}({args_str}):\n{indent_str}{body}\n'
        raise NotImplementedError(self)

    def format(self, indent: int = 0) -> Text:
        return textwrap.indent(self._format(), ' ' * indent)


class Block:
    def __init__(self, stmts: Sequence[Stmt]):
        self.stmts = tuple(stmts)

    def format(self, indent: int = 0):
        return '\n'.join(s.format() for s in self.stmts) + '\n'


class ExprKind(enum.Enum):
    INVOKE = 'invoke'
    DICT_LITERAL = 'dict-literal'
    NAME_REF = 'name-ref'
    NONE_LITERAL = 'none-literal'
    GETATTR = 'getattr'


class Expr:
    @classmethod
    def make_dict_literal(cls):
        return cls(ExprKind.DICT_LITERAL, operands=())

    @classmethod
    def make_none(cls):
        return cls(ExprKind.NONE_LITERAL, operands=())

    @classmethod
    def make_invoke(cls, lhs: 'Expr', args: Tuple['Expr', ...]) -> 'Expr':
        return cls(ExprKind.INVOKE, (lhs, args))

    @classmethod
    def make_name_ref(cls, arg: NameDef) -> 'Expr':
        assert isinstance(arg, NameDef), repr(arg)
        return cls(ExprKind.NAME_REF, (arg,))

    @classmethod
    def make_getattr(cls, lhs: 'Expr', name: Text) -> 'Expr':
        return cls(ExprKind.GETATTR, (lhs, name))

    def __init__(self, kind: ExprKind, operands: Tuple['Expr', ...]):
        assert isinstance(operands, tuple), operands
        self.kind = kind
        self.operands = operands

    def __repr__(self) -> Text:
        return f'{self.__class__.__name__}({self.kind}, {self.operands})'

    def _format(self) -> Text:
        if self.kind == ExprKind.DICT_LITERAL:
            return '{}'
        if self.kind == ExprKind.NONE_LITERAL:
            return 'None'
        if self.kind == ExprKind.NAME_REF:
            name_def = self.operands[0]
            assert isinstance(name_def, NameDef), repr(name_def)
            return '{}'.format(name_def.name)
        if self.kind == ExprKind.INVOKE:
            lhs, args = self.operands
            assert isinstance(args, tuple), args
            return '{}({})'.format(
                lhs.format(), ', '.join(a.format() for a in args))
        if self.kind == ExprKind.GETATTR:
            return '({}).{}'.format(self.operands[0].format(),
                                    self.operands[1])
        raise NotImplementedError(self)

    def format(self, indent: int = 0) -> Text:
        return textwrap.indent(self._format(), ' ' * indent)
