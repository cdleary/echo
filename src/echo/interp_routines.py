import functools
import operator
import os
import sys
import types
from typing import Text, Any, Union, Dict, Callable
import weakref

from echo.elog import log, debugged
from echo.interp_context import ICtx
from echo.interp_result import Result, check_result, ExceptionData
from echo.epy_object import AttrWhere
from echo.interpreter_state import InterpreterState
from echo.eobjects import (
    EInstance, EBuiltin, EFunction, EClass,
    EPyObject, EMethod,
    get_guest_builtin,
    do_hasattr,
)
from echo.emodule import EModule
from echo.value import Value

import termcolor


OPNAME_TO_SPECIAL = {
    'BINARY_SUBTRACT': '__sub__',
    'BINARY_ADD': '__add__',
    'BINARY_SUBSCR': '__getitem__',
    'BINARY_AND': '__and__',
    'BINARY_MULTIPLY': '__mul__',
}
OPNAME_TO_SPECIAL_RHS = {
    'BINARY_ADD': '__radd__',
    'BINARY_SUBTRACT': '__rsub__',
    'BINARY_MULTIPLY': '__rmul__',
    'BINARY_AND': '__rand__',
}
COMPARE_TO_SPECIAL = {
    '==': '__eq__',
    '!=': '__ne__',
    '<': '__lt__',
    '>': '__gt__',
    '>=': '__ge__',
    '<=': '__le__',
    'in': '__contains__',
    'not in': '__contains__',
}
GUEST_BUILTIN_NAMES = (
    'Exception',
    'any',
    'bool',
    'callable',
    'classmethod',
    'dict',
    'dir',
    'enumerate',
    'getattr',
    'hasattr',
    'int',
    'isinstance',
    'issubclass',
    'iter',
    'len',
    'list',
    'map',
    'max',
    'min',
    'next',
    'object',
    'property',
    'repr',
    'reversed',
    'staticmethod',
    'str',
    'super',
    'tuple',
    'type',
    'zip',
)
BUILTIN_EXCEPTION_TYPES = (
    AssertionError,
    AttributeError,
    ImportError,
    NameError,
    NotImplementedError,
    StopIteration,
    ValueError,
    TypeError,
)
BUILTIN_WARNING_TYPES = (
    Warning,
    DeprecationWarning,
)
COMPARE_OPS = {
    '==': operator.eq,
    '!=': operator.ne,
    '<': operator.lt,
    '>': operator.gt,
    '>=': operator.ge,
    '<=': operator.le,
    'is not': operator.is_not,
    'is': operator.is_,
    'in': lambda a, b: operator.contains(b, a),
    'not in': lambda a, b: not operator.contains(b, a),
}
BUILTIN_VALUE_TYPES = {
    int,
    float,
    range,
    str,
    bytes,
    tuple,
    slice,
    set,
    bytearray,
    type(None),
    type(sys.version_info),
}
CODE_ATTRS = [
    'co_argcount', 'co_cellvars', 'co_code', 'co_consts', 'co_filename',
    'co_firstlineno', 'co_flags', 'co_freevars', 'co_kwonlyargcount',
    'co_lnotab', 'co_name', 'co_names', 'co_nlocals', 'co_stacksize',
    'co_varnames',
]
BUILTIN_VALUE_TYPES_TUP = tuple(BUILTIN_VALUE_TYPES)


def _egetitem(x, y):
    log('ir:getitem', f'x: {x} y: {y}')
    if isinstance(x, dict):
        if y not in x:
            return ExceptionData(None, None, KeyError(y))
    try:
        return operator.getitem(x, y)
    except IndexError as e:
        return ExceptionData(None, None, e)


_BINARY_OPS = {
    'BINARY_LSHIFT': operator.lshift,
    'BINARY_RSHIFT': operator.rshift,
    'BINARY_ADD': operator.add,
    'BINARY_AND': operator.and_,
    'BINARY_OR': operator.or_,
    'BINARY_MODULO': operator.mod,
    'BINARY_MULTIPLY': operator.mul,
    'BINARY_SUBTRACT': operator.sub,
    'BINARY_SUBSCR': _egetitem,
    'BINARY_TRUE_DIVIDE': operator.truediv,
    'BINARY_FLOOR_DIVIDE': operator.floordiv,
}
_UNARY_OPS = {
    'UNARY_INVERT': operator.invert,
    'UNARY_NEGATIVE': operator.neg,
}


@check_result
def run_unop(opname: Text, arg: Any, ictx: ICtx) -> Result[Any]:
    op = _UNARY_OPS[opname]
    if type(arg) in BUILTIN_VALUE_TYPES:
        return Result(op(arg))
    raise NotImplementedError(opname)


@check_result
def run_binop(opname: Text, lhs: Any, rhs: Any, ictx: ICtx) -> Result[Any]:
    if (opname in ('BINARY_TRUE_DIVIDE', 'BINARY_MODULO') and type(rhs) is int
            and rhs == 0):
        raise NotImplementedError(opname, lhs, rhs)

    if {type(lhs), type(rhs)} <= BUILTIN_VALUE_TYPES or (
            type(lhs) in (list, dict, types.MappingProxyType, bytearray)
            and opname == 'BINARY_SUBSCR') or (
            type(lhs) == type(rhs) == list and opname == 'BINARY_ADD') or (
            type(lhs) == list and type(rhs) == int
            and opname == 'BINARY_MULTIPLY') or (
            type(lhs) == type(rhs) == set and opname == 'BINARY_SUBTRACT') or (
            type(lhs) is str and opname == 'BINARY_MODULO'):
        op = _BINARY_OPS[opname]
        return Result(op(lhs, rhs))

    if opname in OPNAME_TO_SPECIAL and isinstance(lhs, EPyObject):
        special_f = lhs.getattr(OPNAME_TO_SPECIAL[opname], ictx)
        if special_f.is_exception():
            raise NotImplementedError(special_f)
        return special_f.get_value().invoke((rhs,), {}, {}, ictx)

    if opname in OPNAME_TO_SPECIAL_RHS and isinstance(rhs, EPyObject):
        special_f = rhs.getattr(OPNAME_TO_SPECIAL_RHS[opname], ictx)
        if special_f.is_exception():
            raise NotImplementedError(special_f)
        return special_f.get_value().invoke((lhs,), {}, {}, ictx)

    raise NotImplementedError(opname, lhs, rhs)


def code_to_str(c: types.CodeType) -> Text:
    guts = ', '.join('{}={!r}'.format(attr.split('_')[1], getattr(c, attr))
                     for attr in CODE_ATTRS)
    return 'Code({})'.format(guts)


def exception_match(lhs, rhs, ictx: ICtx) -> Result[Any]:
    if lhs is rhs:
        r = Result(True)
    else:
        do_isinstance = get_guest_builtin('isinstance')
        r = do_isinstance.invoke((lhs, rhs), {}, {}, ictx)
    log('ir:em', f'lhs {lhs!r} rhs {rhs!r} => {r}')
    return r


@check_result
def compare(opname: Text, lhs, rhs, ictx: ICtx) -> Result[bool]:
    if (isinstance(lhs, BUILTIN_VALUE_TYPES_TUP)
            and isinstance(rhs, BUILTIN_VALUE_TYPES_TUP)):
        return Result(COMPARE_OPS[opname](lhs, rhs))
    if {type(lhs), type(rhs)} == {str, tuple} and opname == '==':
        return Result(False)
    if {type(lhs), type(rhs)} == {int, tuple} and opname == '==':
        return Result(False)

    if isinstance(lhs, dict) and isinstance(rhs, dict) and opname == '==':
        f = get_guest_builtin('dict.__eq__')
        return f.invoke((lhs, rhs), {}, {}, ictx)

    if isinstance(lhs, list) and isinstance(rhs, list) and opname == '==':
        f = get_guest_builtin('list.__eq__')
        return f.invoke((lhs, rhs), {}, {}, ictx)

    if opname in ('in', 'not in') and type(rhs) in (
            tuple, dict, set, frozenset, type(os.environ),
            weakref.WeakSet):
        for e in rhs:
            e_result = compare('==', lhs, e, ictx)
            if e_result.is_exception():
                return e_result
            if e_result.get_value():
                return Result(opname == 'in')
        return Result(opname == 'not in')

    if opname in ('is', 'is not'):
        op = COMPARE_OPS[opname]
        return Result(op(lhs, rhs))

    if (opname in COMPARE_TO_SPECIAL and
            (isinstance(lhs, EInstance) or
             (isinstance(rhs, EInstance) and opname in ('in', 'not in')))):
        log('ir:cmp', f'opname: {opname!r} lhs: {lhs!r} rhs: {rhs!r}')
        lhs, rhs = (rhs, lhs) if opname in ('in', 'not in') else (lhs, rhs)
        log('ir:cmp', f'opname: {opname!r} lhs: {lhs!r} rhs: {rhs!r}')
        special_f = lhs.getattr(COMPARE_TO_SPECIAL[opname], ictx)
        if special_f.is_exception():
            return Result(special_f.get_exception())
        f = special_f.get_value()
        log('ir:cmp', f'special function for {opname!r}: {special_f}')
        r = f.invoke((rhs,), {}, {}, ictx)
        log('ir:cmp', f'special function for {opname!r}: {special_f} => {r}')
        if r.is_exception():
            return r
        if opname == 'not in':
            assert isinstance(r.get_value(), bool), r
            return Result(not r.get_value())
        return r

    def is_set_of_strings(x: Any) -> bool:
        return isinstance(x, set) and all(isinstance(e, str) for e in x)

    if is_set_of_strings(lhs) and is_set_of_strings(rhs):
        return Result(lhs == rhs)

    if isinstance(lhs, EClass) and isinstance(rhs, EClass):
        return Result(lhs is rhs)

    if (opname == '==' and isinstance(lhs, EClass)
            and not isinstance(rhs, EClass)
            and not lhs.hasattr('__eq__')):
        return Result(False)

    if (opname == '==' and not isinstance(rhs, EClass)
            and isinstance(lhs, EClass)):
        return Result(False)

    if (not isinstance(lhs, EPyObject)
            and not isinstance(rhs, EPyObject)):
        return Result(COMPARE_OPS[opname](lhs, rhs))

    if (opname == '!=' and isinstance(lhs, EMethod)
            and not isinstance(rhs, EPyObject)):
        return Result(True)

    if (opname == '==' and isinstance(lhs, EBuiltin)
            and isinstance(rhs, EBuiltin)):
        return Result(lhs is rhs)

    def symmetrical_isinstance(cls0, cls1):
        return ((isinstance(lhs, cls0) and isinstance(rhs, cls1)) or
                (isinstance(lhs, cls1) and isinstance(rhs, cls0)))

    if opname == '==' and symmetrical_isinstance(EBuiltin, EFunction):
        return Result(False)

    if (opname == '==' and isinstance(lhs, (EBuiltin, EFunction))
            and rhs is None):
        return Result(False)

    if (opname == '==' and isinstance(lhs, EFunction)
            and isinstance(rhs, EFunction)):
        return Result(lhs is rhs)

    if isinstance(lhs, int) and opname in COMPARE_TO_SPECIAL:
        fcmp = get_guest_builtin('int.{}'.format(COMPARE_TO_SPECIAL[opname]))
        return fcmp.invoke((lhs, rhs), {}, {}, ictx)

    if isinstance(lhs, EBuiltin) and isinstance(rhs, type):
        return Result(False)

    raise NotImplementedError(opname, lhs, rhs)


def _name_is_from_metaclass(cls: EClass, name: Text) -> bool:
    for c in cls.get_mro():
        if not isinstance(c, EClass):
            continue
        if name in c.dict_:
            return False
        if c.metaclass and c.metaclass.hasattr(name):
            return True
    return False


@debugged('ir:mrs')
def method_requires_self(obj: Any, name: Text, value: Any) -> bool:
    if isinstance(value, EBuiltin) and value.bound_self is not None:
        return False
    if isinstance(obj, EPyObject):
        type_ = obj.get_type()
        if not type_.has_standard_getattr():
            return False
        where = obj.hasattr_where(name)
        log('ir:mrs',
            f'attr {name} on {obj!r} (type {type_}) is {where} '
            f'(value {value})')
        assert where is not None
        return where == AttrWhere.CLS and not isinstance(value, EMethod)

    result = (
        hasattr(type(obj), name)
        and not isinstance(value, (types.BuiltinMethodType, types.MethodType)))
    log('ir:mrs', f'attr {name} on {obj!r} type {type(obj)} => {result}')
    return result


def cprint(msg, color, file=sys.stderr, end='\n') -> None:
    termcolor.cprint(msg, color=color, file=file, end=end)


def cprint_lines_after(filename: Text, lineno: int) -> None:
    with open(filename) as f:
        lines = f.readlines()
    lines = lines[lineno-1:]
    saw_def = False
    for lineno, line in enumerate(lines, lineno-1):
        # TODO(cdleary, 2019-01-24): Should detect the original indent level
        # and terminate the line printout at the first point where the indent
        # decreases (first dedent).
        if line.startswith('def'):
            if saw_def:
                break
            else:
                saw_def = True
        cprint('%05d: ' % lineno, color='yellow', end='')
        cprint(line.rstrip(), color='blue')
