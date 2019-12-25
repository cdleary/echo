import types
import weakref
from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject
from echo.interp_result import Result, ExceptionData, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin, EClass, EInstance,
    register_builtin, _is_dict_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx


_ITER_BUILTIN_TYPES = (
    tuple, str, bytes, bytearray, type({}.keys()), type({}.values()),
    type({}.items()), list, type(reversed([])), type(range(0, 0)),
    set, type(zip((), ())), frozenset, weakref.WeakSet, dict,
)


@register_builtin('iter')
@check_result
def _do_iter(args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
    assert len(args) == 1

    if isinstance(args[0], _ITER_BUILTIN_TYPES):
        return Result(iter(args[0]))

    if isinstance(args[0], EPyObject) and args[0].hasattr('__iter__'):
        iter_f = args[0].getattr('__iter__', ictx)
        if iter_f.is_exception():
            return iter_f
        iter_f = iter_f.get_value()
        return iter_f.invoke((), {}, {}, ictx)

    if isinstance(args[0], EPyObject) and hasattr(args[0], 'iter'):
        return args[0].iter(ictx)

    raise NotImplementedError(args[0], type(args[0]))


TUPLE_ITERATOR = type(iter(()))
STR_ITERATOR = type(iter(''))
BYTES_ITERATOR = type(iter(b''))
LIST_ITERATOR = type(iter([]))
LIST_REV_ITERATOR = type(reversed([]))
DICT_ITERATOR = type(iter({}))
DICT_ITERATOR = type(iter(set([])))
DICT_KEY_ITERATOR = type(iter({}.keys()))
DICT_ITEM_ITERATOR = type(iter({}.items()))
RANGE_ITERATOR = type(iter(range(0)))
ZIP_ITERATOR = type(iter(zip((), ())))
BUILTIN_ITERATORS = (
    TUPLE_ITERATOR, LIST_ITERATOR, LIST_REV_ITERATOR, DICT_ITERATOR,
    RANGE_ITERATOR, DICT_KEY_ITERATOR, ZIP_ITERATOR, DICT_ITEM_ITERATOR,
    STR_ITERATOR, BYTES_ITERATOR,
    types.GeneratorType
)


@register_builtin('next')
@check_result
def _do_next(args: Tuple[Any, ...],
             kwargs: Dict[Text, Any], ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    g = args[0]
    if isinstance(g, BUILTIN_ITERATORS):
        try:
            return Result(next(g))
        except StopIteration as e:
            return Result(ExceptionData(None, None, e))
    if isinstance(g, EPyObject) and g.hasattr('__next__'):
        f = g.getattr('__next__', ictx)
        if f.is_exception():
            return f
        f = f.get_value()
        return f.invoke((), {}, {}, ictx)
    return g.next(ictx)
