import functools
import operator
import os
import sys
import types
from typing import Text, Any, Union, Dict, Callable
import weakref

from echo.interp_context import ICtx
from echo.interp_result import Result, check_result
from echo.interpreter_state import InterpreterState
from echo.guest_objects import (
    GuestInstance, GuestBuiltin, GuestModule, GuestFunction, GuestClass,
    get_guest_builtin, GuestPyObject, GuestClassMethod, GuestMethod
)
from echo.value import Value

import termcolor


OPNAME_TO_SPECIAL = {
    'BINARY_SUBTRACT': '__sub__',
    'BINARY_ADD': '__add__',
}
COMPARE_TO_SPECIAL = {
    '==': '__eq__',
    '<': '__lt__',
    '>': '__gt__',
}
GUEST_BUILTIN_NAMES = (
    'isinstance', 'issubclass', 'super', 'iter', 'type', 'zip', 'reversed',
    'next', 'hasattr', 'repr', 'dir', 'object', 'classmethod', 'staticmethod',
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
}
BUILTIN_VALUE_TYPES = {
    int,
    float,
    str,
    tuple,
    slice,
    type(None),
}
CODE_ATTRS = [
    'co_argcount', 'co_cellvars', 'co_code', 'co_consts', 'co_filename',
    'co_firstlineno', 'co_flags', 'co_freevars', 'co_kwonlyargcount',
    'co_lnotab', 'co_name', 'co_names', 'co_nlocals', 'co_stacksize',
    'co_varnames',
]
BUILTIN_VALUE_TYPES_TUP = tuple(BUILTIN_VALUE_TYPES)
_BINARY_OPS = {
    'BINARY_LSHIFT': operator.lshift,
    'BINARY_RSHIFT': operator.rshift,
    'BINARY_ADD': operator.add,
    'BINARY_MODULO': operator.mod,
    'BINARY_MULTIPLY': operator.mul,
    'BINARY_SUBTRACT': operator.sub,
    'BINARY_SUBSCR': operator.getitem,
    'BINARY_TRUE_DIVIDE': operator.truediv,
    'BINARY_FLOOR_DIVIDE': operator.floordiv,
}


@check_result
def run_binop(opname: Text, lhs: Any, rhs: Any, ictx: ICtx) -> Result[Any]:
    if (opname in ('BINARY_TRUE_DIVIDE', 'BINARY_MODULO') and type(rhs) is int
            and rhs == 0):
        raise NotImplementedError(opname, lhs, rhs)
    if {type(lhs), type(rhs)} <= BUILTIN_VALUE_TYPES or (
            type(lhs) in (list, dict, types.MappingProxyType)
            and opname == 'BINARY_SUBSCR') or (
            type(lhs) == type(rhs) == list and opname == 'BINARY_ADD') or (
            type(lhs) == type(rhs) == set and opname == 'BINARY_SUBTRACT') or (
            type(lhs) is str and opname == 'BINARY_MODULO'):
        op = _BINARY_OPS[opname]
        return Result(op(lhs, rhs))

    if opname in OPNAME_TO_SPECIAL and isinstance(lhs, GuestInstance):
        special_f = lhs.getattr(OPNAME_TO_SPECIAL[opname], ictx)
        if special_f.is_exception():
            raise NotImplementedError(special_f)
        return special_f.get_value().invoke((rhs,), {}, {}, ictx)

    raise NotImplementedError(opname, lhs, rhs)


def code_to_str(c: types.CodeType) -> Text:
    guts = ', '.join('{}={!r}'.format(attr.split('_')[1], getattr(c, attr))
                     for attr in CODE_ATTRS)
    return 'Code({})'.format(guts)


def builtins_get(builtins: Union[types.ModuleType, Dict], name: Text) -> Any:
    if name in GUEST_BUILTIN_NAMES:
        return get_guest_builtin(name)
    if isinstance(builtins, types.ModuleType):
        return getattr(builtins, name)
    return builtins[name]


def exception_match(lhs, rhs) -> bool:
    if set([lhs, rhs]) <= set(BUILTIN_EXCEPTION_TYPES):
        return issubclass(lhs, rhs)
    if isinstance(lhs, rhs):
        return True
    raise NotImplementedError(lhs, rhs)


@check_result
def compare(opname: Text, lhs, rhs, ictx: ICtx) -> Result[bool]:
    if (isinstance(lhs, BUILTIN_VALUE_TYPES_TUP)
            and isinstance(rhs, BUILTIN_VALUE_TYPES_TUP)):
        return Result(COMPARE_OPS[opname](lhs, rhs))
    if {type(lhs), type(rhs)} == {str, tuple} and opname == '==':
        return Result(False)
    if {type(lhs), type(rhs)} == {int, tuple} and opname == '==':
        return Result(False)
    if (isinstance(lhs, (list, tuple)) and isinstance(rhs, (list, tuple))
            and opname == '=='):
        if len(lhs) != len(rhs):
            return Result(False)
        for e, f in zip(lhs, rhs):
            e_result = compare(opname, e, f, ictx)
            if e_result.is_exception():
                return e_result
            if not e_result.get_value():
                return Result(False)
        return Result(True)

    if isinstance(lhs, dict) and isinstance(rhs, dict):
        if len(lhs) != len(rhs):
            return Result(False)
        for k in set(lhs.keys()) | set(rhs.keys()):
            if k not in lhs or k not in rhs:
                return Result(False)
            e_result = compare(opname, lhs[k], rhs[k], ictx)
            if e_result.is_exception():
                return e_result
            if not e_result.get_value():
                return Result(False)
        return Result(True)

    if opname in ('in', 'not in') and type(rhs) in (
            tuple, list, dict, set, frozenset, type(os.environ),
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

    if opname in COMPARE_TO_SPECIAL and isinstance(lhs, GuestInstance):
        special_f = lhs.getattr(COMPARE_TO_SPECIAL[opname], ictx)
        if special_f.is_exception():
            return Result(special_f.get_exception())
        return special_f.get_value().invoke((rhs,), {}, {}, ictx)

    def is_set_of_strings(x: Any) -> bool:
        return isinstance(x, set) and all(isinstance(e, str) for e in x)

    if is_set_of_strings(lhs) and is_set_of_strings(rhs):
        return Result(lhs == rhs)

    if isinstance(lhs, GuestClass) and isinstance(rhs, GuestClass):
        return Result(lhs is rhs)

    if (opname == '==' and isinstance(lhs, GuestClass)
            and not isinstance(rhs, GuestClass)
            and not lhs.hasattr('__eq__')):
        return Result(False)

    if (opname == '==' and not isinstance(rhs, GuestClass)
            and isinstance(lhs, GuestClass)):
        return Result(False)

    if (not isinstance(lhs, GuestPyObject)
            and not isinstance(rhs, GuestPyObject)):
        return Result(COMPARE_OPS[opname](lhs, rhs))

    if (opname == '!=' and isinstance(lhs, GuestMethod)
            and not isinstance(rhs, GuestPyObject)):
        return Result(True)

    raise NotImplementedError(opname, lhs, rhs, type(rhs))


def debugged(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        result = f(*args, **kwargs)
        print(f.__name__, 'args:', args, 'kwargs:', kwargs, '=>', result)
        return result
    return wrapper


def _name_is_from_metaclass(cls: GuestClass, name: Text):
    for c in cls.get_mro():
        if not isinstance(c, GuestClass):
            continue
        if name in c.dict_:
            return False
        if c.metaclass and c.metaclass.hasattr(name):
            return True
    return False


def method_requires_self(obj: Any, name: Text, value: Any) -> bool:
    obj_is_module = isinstance(obj, GuestModule)
    if isinstance(value, GuestBuiltin) and value.bound_self is None:
        return not obj_is_module
    if isinstance(value, types.MethodType):
        return False
    if isinstance(value, GuestFunction):
        if isinstance(obj, GuestClass):
            return _name_is_from_metaclass(obj, name)
        if isinstance(obj, GuestInstance):
            return value not in obj.dict_.values()
        return not obj_is_module
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
