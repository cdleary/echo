import operator
import os
import sys
import types
from typing import Text, Any, Dict, Callable
import weakref

from echo.dso_objects import DsoPyObject, DsoClassProxy
from echo.ebuiltins import BUILTIN_VALUE_TYPES_TUP, BUILTIN_VALUE_TYPES
from echo.elog import log, debugged
from echo.interp_context import ICtx
from echo.interp_result import Result, check_result, ExceptionData
from echo.epy_object import try_invoke
from echo.eobjects import (
    EInstance, EBuiltin, EFunction, EClass,
    EPyObject, EMethod,
    get_guest_builtin,
    _type_getattro,
)

import termcolor


OPNAME_TO_SPECIAL = {
    'BINARY_SUBTRACT': '__sub__',
    'BINARY_ADD': '__add__',
    'BINARY_SUBSCR': '__getitem__',
    'BINARY_AND': '__and__',
    'BINARY_MULTIPLY': '__mul__',
    'BINARY_OR': '__or__',
    'BINARY_POWER': '__pow__',
}
OPNAME_TO_SPECIAL_RHS = {
    'BINARY_ADD': '__radd__',
    'BINARY_SUBTRACT': '__rsub__',
    'BINARY_MULTIPLY': '__rmul__',
    'BINARY_AND': '__rand__',
    'BINARY_OR': '__ror__',
    'BINARY_POWER': '__rpow__',
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
CODE_ATTRS = [
    'co_argcount', 'co_cellvars', 'co_code', 'co_consts', 'co_filename',
    'co_firstlineno', 'co_flags', 'co_freevars', 'co_kwonlyargcount',
    'co_lnotab', 'co_name', 'co_names', 'co_nlocals', 'co_stacksize',
    'co_varnames',
]


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
    'BINARY_POWER': operator.pow,
}
_UNARY_OPS: Dict[str, Callable[[Any], Any]] = {
    'UNARY_INVERT': operator.invert,
    'UNARY_NEGATIVE': operator.neg,
    'UNARY_POSITIVE': operator.pos,
}


@check_result
def run_unop(opname: Text, arg: Any, ictx: ICtx) -> Result[Any]:
    op: Callable[[Any], Any] = _UNARY_OPS[opname]
    if type(arg) in BUILTIN_VALUE_TYPES:
        return Result(op(arg))
    raise NotImplementedError(opname)


@check_result
def run_binop(opname: Text, lhs: Any, rhs: Any, ictx: ICtx) -> Result[Any]:
    do_type = get_guest_builtin('type')
    lhs_type = do_type.invoke((lhs,), {}, {}, ictx).get_value()
    rhs_type = do_type.invoke((rhs,), {}, {}, ictx).get_value()
    ebool = get_guest_builtin('bool')
    ebytes = get_guest_builtin('bytes')
    estr = get_guest_builtin('str')
    eint = get_guest_builtin('int')
    elist = get_guest_builtin('list')
    edict = get_guest_builtin('dict')
    ebytearray = get_guest_builtin('bytearray')
    eset = get_guest_builtin('set')
    etuple = get_guest_builtin('tuple')
    builtin_value_types = {
        ebool, ebytes, estr, eint, elist, edict, ebytearray, eset, etuple,
        float, complex, slice, range, ebytearray, type(sys.version_info),
    }

    if (opname in ('BINARY_TRUE_DIVIDE', 'BINARY_MODULO') and rhs_type is eint
            and rhs == 0):
        raise NotImplementedError(opname, lhs, rhs)

    if (({lhs_type, rhs_type} <= builtin_value_types) or
        (lhs_type in (elist, edict, types.MappingProxyType, ebytearray)
            and opname == 'BINARY_SUBSCR') or
        (lhs_type == rhs_type == elist and opname == 'BINARY_ADD') or
        (lhs_type == elist and rhs_type == eint
            and opname == 'BINARY_MULTIPLY') or
        (lhs_type == rhs_type == eset and opname == 'BINARY_SUBTRACT') or
        (lhs_type is estr
            and opname == 'BINARY_MODULO')):
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

    raise NotImplementedError(opname, lhs, rhs, lhs_type, rhs_type)


def code_to_str(c: types.CodeType) -> Text:
    guts = ', '.join('{}={!r}'.format(attr.split('_')[1], getattr(c, attr))
                     for attr in CODE_ATTRS)
    return 'Code({})'.format(guts)


def exception_match(lhs, rhs, ictx: ICtx) -> Result[Any]:
    if isinstance(rhs, tuple):
        return Result(any(exception_match(lhs, e, ictx) for e in rhs))
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
            tuple, list, dict, set, frozenset, type(os.environ),
            type({}.values()),
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

    def symmetric_isinstance(atype, btype):
        return ((isinstance(lhs, atype) and isinstance(rhs, btype)) or
                (isinstance(lhs, btype) and isinstance(rhs, atype)))

    if (symmetric_isinstance(type, DsoPyObject) or
            symmetric_isinstance(EBuiltin, DsoPyObject)):
        return Result(False)

    if (opname == '==' and isinstance(lhs, DsoClassProxy) and
            isinstance(rhs, DsoClassProxy)):
        return Result(lhs.wrapped == rhs.wrapped)

    if (isinstance(lhs, EPyObject) and
            lhs.get_type().hasattr(COMPARE_TO_SPECIAL[opname])):
        f_cmp_ = lhs.getattr(COMPARE_TO_SPECIAL[opname], ictx)
        if f_cmp_.is_exception():
            return f_cmp_
        f_cmp = f_cmp_.get_value()
        return try_invoke(f_cmp, (rhs,), {}, {}, ictx)

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
def method_requires_self(obj: Any, name: Text, value: Any, ictx: ICtx) -> bool:
    do_type = get_guest_builtin('type')
    if not isinstance(do_type, EClass):
        return False
    t = do_type.invoke((obj,), {}, {}, ictx).get_value()
    r = _type_getattro(t, name, ictx, do_invoke_desc=False)
    assert isinstance(r, tuple)
    is_desc, attr = r
    return False


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


def dict_merge_with_error(d: Any, e: Any) -> Result[None]:
    for k, v in e.items():
        if k in d:
            return Result(ExceptionData(None, None, KeyError(k)))
        d[k] = v
    return Result(None)
