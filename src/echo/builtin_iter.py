import itertools
import types
import weakref
from typing import Text, Tuple, Any, Dict, Optional, Type
from collections import OrderedDict as odict

from echo.epy_object import EPyObject, AttrWhere, EPyType, try_invoke
from echo.enative_fn import ENativeFn
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EMethod, register_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx


_ITER_BUILTIN_TYPES: Tuple[Type, ...] = (
    tuple, type(''), type(b''), type(bytearray()), type({}.keys()),
    type({}.values()), type({}.items()), type([]), type(reversed([])),
    type(range(0, 0)), type(set()), type(zip((), ())), type(frozenset()),
    type(weakref.WeakSet()), type(dict()),
    type(itertools.permutations(())),
)


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

    def get_type(self) -> EPyType:
        return get_guest_builtin('type')

    def get_mro(self) -> Tuple[EPyType, ...]:
        return (self, get_guest_builtin('object'))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__mro__':
            return Result(self.get_mro())
        if name == '__dict__':
            return Result(self._dict)
        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
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

    def get_type(self) -> EPyType:
        return SeqIterType_singleton

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__next__':
            return Result(EMethod(
                ENativeFn(self.next, 'seqiter.__next__'),
                bound_self=self))
        raise NotImplementedError(self, name)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name == '__next__':
            return AttrWhere.SELF_SPECIAL
        return None

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError(self, name, value)

    def next(self, args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx,
             globals_: Optional[Dict[Text, Any]] = None
             ) -> Result[Any]:
        assert len(args) == 1 and not kwargs, (args, kwargs)
        gi_ = self.subject.getattr('__getitem__', ictx)
        if gi_.is_exception():
            return gi_
        gi = gi_.get_value()
        res = try_invoke(gi, (self.next_index,), {}, {}, ictx)
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
        iter_f_ = args[0].getattr('__iter__', ictx)
        if iter_f_.is_exception():
            return iter_f_
        iter_f = iter_f_.get_value()
        return try_invoke(iter_f, (), {}, {}, ictx)

    if isinstance(args[0], EPyObject):
        it = getattr(args[0], 'iter', None)
        if it is not None:
            return it(ictx)

        if args[0].hasattr('__getitem__'):
            return Result(SeqIter(args[0]))

        type_name = args[0].get_type().get_name()
        return Result(ExceptionData(
            None, None, TypeError(f'{type_name!r} object is not iterable')))

    raise NotImplementedError(args[0], type(args[0]))


BUILTIN_ITERATORS: Tuple[Type, ...] = (
    type(iter(())),
    type(iter('')),
    type(iter(b'')),
    type(iter([])),
    type(reversed([])),
    type(iter({})),
    type(iter(set([]))),
    type(iter({}.keys())),
    type(iter({}.values())),
    type(iter({}.items())),
    type(iter(range(0))),
    type(iter(zip((), ()))),
    type(iter(odict())),
    types.GeneratorType,
    type(itertools.permutations(())),
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
        f_ = g.getattr('__next__', ictx)
        if f_.is_exception():
            return f_
        f = f_.get_value()
        return try_invoke(f, (), {}, {}, ictx)
    return g.next(ictx)
