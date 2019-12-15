import itertools
from typing import Text, Tuple, Any, Dict, Optional

from echo.elog import log
from echo.epy_object import EPyObject, AttrWhere
from echo.interp_result import Result, check_result
from echo import interp_routines
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin, EClass, EInstance,
    register_builtin, _is_dict_builtin, get_guest_builtin,
)
from echo.interp_context import ICtx


class EEnumerate(EPyObject):
    def __init__(self, iterator):
        self.iterator = iterator
        self._count = itertools.count(0)

    def get_type(self) -> 'EPyObject':
        return get_guest_builtin('enumerate')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, *args, **kwargs) -> Result[None]:
        raise NotImplementedError

    def next(self, ictx: ICtx) -> Result[Any]:
        do_next = get_guest_builtin('next')
        v = do_next.invoke((self.iterator,), {}, {}, ictx)
        if v.is_exception():
            return v
        return Result((next(self._count), v.get_value()))

    def iter(self, ictx) -> Result[Any]:
        return Result(self)


@register_builtin('enumerate')
@check_result
def _do_enumerate(args: Tuple[Any, ...],
                  kwargs: Dict[Text, Any],
                  ictx: ICtx) -> Result[Any]:
    do_iter = get_guest_builtin('iter')
    it = do_iter.invoke((args[0],), {}, {}, ictx)
    if it.is_exception():
        return it
    return Result(EEnumerate(it.get_value()))
