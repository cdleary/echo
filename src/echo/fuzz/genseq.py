import enum
import textwrap
from typing import Tuple, Text, Any, Sequence, Optional


INDENT_PER_LEVEL = 4


class StmtKind(enum.Enum):
    ASSIGN = 'assign'
    EXPR = 'expr'
    CLASS_DEF = 'class-def'
    FN_DEF = 'fn-def'
    RETURN = 'return'
    PASS = 'pass'
    IF = 'if'
    TRY = 'try'


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
    def make_if(cls, test: 'Expr', consequent: 'Suite',
                elifs: Tuple[Tuple['Expr', 'Suite'], ...],
                alternate: Optional['Suite']) -> 'Stmt':
        return cls(StmtKind.IF, (test, consequent, elifs, alternate))

    @classmethod
    def make_try(cls, consequent: 'Suite',
                 excepts: Sequence[Tuple['As', 'Suite']],
                 finally_: Optional['Suite']) -> 'Stmt':
        return cls(StmtKind.TRY, (consequent, tuple(excepts), finally_))

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
        if self.kind == StmtKind.EXPR:
            assert len(self.operands) == 1, self.operands
            return self.operands[0].format()
        if self.kind == StmtKind.ASSIGN:
            assert len(self.operands) == 2, self.operands
            return '{} = {}'.format(self.operands[0],
                                    self.operands[1].format())
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
        if self.kind == StmtKind.TRY:
            consequent, excepts, finally_ = self.operands
            pieces = ['try:\n']
            pieces.append(consequent.format(INDENT_PER_LEVEL))
            for except_ in excepts:
                pieces.append(f'except {except_[0].format()}:\n')
                pieces.append(except_[1].format(INDENT_PER_LEVEL))
            if finally_:
                pieces.append('finally:\n')
                pieces.append(finally_.format(INDENT_PER_LEVEL))
            return ''.join(pieces)
        if self.kind == StmtKind.IF:
            test, consequent, elifs, alternate = self.operands
            consequent_str = consequent.format(INDENT_PER_LEVEL)
            pieces = [f'if {test.format()}:\n{consequent_str}']
            for elif_ in elifs:
                suite_str = elif_[1].format(INDENT_PER_LEVEL)
                pieces.append(f'elif {elif_[0]}:\n{suite_str}')
            if alternate:
                suite_str = alternate.format(INDENT_PER_LEVEL)
                pieces.append(f'else:{suite_str}')
            return ''.join(pieces)
        raise NotImplementedError(self)

    def format(self, indent: int = 0) -> Text:
        return textwrap.indent(self._format(), ' ' * indent)


class Suite:
    def __init__(self, stmts: Sequence[Stmt]):
        self.stmts = tuple(stmts)

    def format(self, indent: int = 0):
        return '\n'.join(s.format(indent) for s in self.stmts) + '\n'


class ExprKind(enum.Enum):
    INVOKE = 'invoke'
    DICT_LITERAL = 'dict-literal'
    STR_LITERAL = 'str-literal'
    NONE_LITERAL = 'none-literal'
    GETATTR = 'getattr'


class Expr:
    """
    TODO(cdleary): 2024-04-28 I think the original instinct here was to try to
    keep it flat, but hard to do without proper sum types... should probably
    switch it to be OOPy.
    """

    @classmethod
    def make_dict_literal(cls):
        return cls(ExprKind.DICT_LITERAL, operands=())

    @classmethod
    def make_str(cls, s: Text):
        return cls(ExprKind.STR_LITERAL, operands=(), str_payload=s)

    @classmethod
    def make_none(cls):
        return cls(ExprKind.NONE_LITERAL, operands=())

    @classmethod
    def make_invoke(cls, lhs: 'Expr', args: Tuple['Expr', ...]) -> 'Expr':
        assert isinstance(args, tuple), args
        return cls(ExprKind.INVOKE, (lhs, *args))

    @classmethod
    def make_name_ref(cls, arg: NameDef) -> 'NameRef':
        assert isinstance(arg, NameDef), repr(arg)
        return NameRef(arg)

    @classmethod
    def make_getattr(cls, lhs: 'Expr', name: Text) -> 'Expr':
        return cls(ExprKind.GETATTR, (lhs,), str_payload=name)

    def __init__(self, kind: ExprKind, operands: Tuple['Expr', ...],
                 str_payload: Optional[str] = None):
        assert isinstance(operands, tuple), operands
        self.kind = kind
        self.operands = operands
        self.str_payload = str_payload

    def __repr__(self) -> Text:
        return f'{self.__class__.__name__}({self.kind}, {self.operands})'

    def _format(self) -> Text:
        if self.kind == ExprKind.DICT_LITERAL:
            return '{}'
        if self.kind == ExprKind.NONE_LITERAL:
            return 'None'
        if self.kind == ExprKind.STR_LITERAL:
            return repr(self.str_payload)
        if self.kind == ExprKind.INVOKE:
            lhs, *args = self.operands
            return '{}({})'.format(
                lhs.format(), ', '.join(a.format() for a in args))
        if self.kind == ExprKind.GETATTR:
            return '({}).{}'.format(self.operands[0].format(),
                                    self.str_payload)
        raise NotImplementedError(self)

    def format(self, indent: int = 0) -> Text:
        return textwrap.indent(self._format(), ' ' * indent)


class NameRef(Expr):
    def __init__(self, name_def: NameDef):
        self.name_def = name_def

    def __repr__(self) -> Text:
        return 'NameRef({!r})'.format(self.name_def)

    def _format(self) -> Text:
        return self.name_def.format()


class As:
    def __init__(self, test: NameRef, binding: Optional[NameDef]):
        self.test = test
        self.binding = binding

    def _format(self) -> Text:
        if self.binding:
            return '{} as {}'.format(self.test.format(), self.binding)
        return str(self.test)

    def format(self, indent: int = 0) -> Text:
        return textwrap.indent(self._format(), ' ' * indent)
