import itertools
import types
import weakref
from typing import Text, Tuple, Any, Dict, Optional, Type
from collections import OrderedDict as odict

from echo.elog import log
from echo.epy_object import EPyObject, AttrWhere, EPyType
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
    itertools.permutations, itertools.product,
)  # type: Tuple[Type, ...]


class SeqIterType(EPyType):
    def __init__(self):
        self._dict = {}

    def get_bases(self):
        raise NotImplementedError

    def get_dict(self):
        raise NotImplementedError

    def get_name(self) -> str:
        return 'iterator'

    def __repr__(self) -> Text:
        return "<eclass 'iterator'>"

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def get_mro(self) -> Tuple[EPyObject, ...]:
        return (self, get_guest_builtin('object'))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__mro__':
            return Result(self.get_mro())
        if name == '__dict__':
            return Result(self._dict)
        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        return None


SeqIterType_singleton = SeqIterType()


class SeqIter(EPyObject):
    def __init__(self, subject: EPyObject):
        self.subject = subject
        self.next_index = 0

    def get_type(self) -> EPyObject:
        return SeqIterType_singleton

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__next__':
            return Result(EMethod(
                NativeFunction(self.next, 'seqiter.__next__'),
                bound_self=self))
        raise NotImplementedError(self, name)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name == '__next__':
            return AttrWhere.SELF_SPECIAL
        return None

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)

    def next(self, args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx,
             globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert len(args) == 1 and not kwargs, (args, kwargs)
        gi = self.subject.getattr('__getitem__', ictx)
        if gi.is_exception():
            return gi
        gi = gi.get_value()
        res = gi.invoke((self.next_index,), {}, {}, ictx)
        if (res.is_exception() and
                isinstance(res.get_exception().exception,
                           (IndexError, StopIteration))):
            return Result(ExceptionData(None, None, StopIteration()))
        if res.is_exception():
            return res
        self.next_index += 1
        return res


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

    if isinstance(args[0], EPyObject):
        if hasattr(args[0], 'iter'):
            return args[0].iter(ictx)

        if args[0].hasattr('__getitem__'):
            return Result(SeqIter(args[0]))

        type_name = args[0].get_type().name
        return Result(ExceptionData(
            None, None, TypeError(f'{type_name!r} object is not iterable')))

    raise NotImplementedError(args[0], type(args[0]))


TUPLE_ITERATOR = type(iter(()))
STR_ITERATOR = type(iter(''))
BYTES_ITERATOR = type(iter(b''))
LIST_ITERATOR = type(iter([]))
LIST_REV_ITERATOR = type(reversed([]))
DICT_ITERATOR = type(iter({}))
DICT_ITERATOR = type(iter(set([])))
DICT_KEY_ITERATOR = type(iter({}.keys()))
DICT_VALUE_ITERATOR = type(iter({}.values()))
DICT_ITEM_ITERATOR = type(iter({}.items()))
RANGE_ITERATOR = type(iter(range(0)))
ZIP_ITERATOR = type(iter(zip((), ())))
BUILTIN_ITERATORS = (
    TUPLE_ITERATOR, LIST_ITERATOR, LIST_REV_ITERATOR,
    RANGE_ITERATOR,
    DICT_KEY_ITERATOR, DICT_ITEM_ITERATOR, DICT_VALUE_ITERATOR, DICT_ITERATOR,
    ZIP_ITERATOR,
    STR_ITERATOR, BYTES_ITERATOR, type(iter(odict())),
    types.GeneratorType, itertools.permutations, itertools.product,
)  # type: Tuple[Type, ...]


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
