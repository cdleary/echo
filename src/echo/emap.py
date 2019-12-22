from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject, AttrWhere
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin,
    get_guest_builtin,
)
from echo.interp_context import ICtx


class EMap(EPyObject):
    def __init__(self, f: EFunction, it):
        self.f = f
        self.it = it

    def get_type(self) -> EPyObject:
        return get_guest_builtin('map')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__get__':
            return Result(EMethod(NativeFunction(
                self._get, 'emap.__get__'), bound_self=self))
        if name == '__get__':
            return Result(EMethod(NativeFunction(
                self._iter, 'emap.__iter__'), bound_self=self))
        return Result(ExceptionData(None, name, AttributeError(name)))

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError

    def iter(self, ictx: ICtx) -> Result[Any]:
        return Result(self)

    def next(self, ictx: ICtx) -> Result[Any]:
        do_next = get_guest_builtin('next')
        res = do_next.invoke((self.it,), {}, {}, ictx)
        if res.is_exception():
            return res
        v = res.get_value()
        return self.f.invoke((v,), {}, {}, ictx)


@check_result
def _do_map(
        args: Tuple[Any, ...],
        kwargs: Optional[Dict[Text, Any]],
        ictx: ICtx) -> Result[Any]:
    if kwargs:
        raise NotImplementedError(kwargs)
    if len(args) != 2:
        raise NotImplementedError(args)
    do_iter = get_guest_builtin('iter')
    it = do_iter.invoke((args[1],), {}, {}, ictx)
    if it.is_exception():
        return it
    e = EMap(args[0], it.get_value())
    return Result(e)


EBuiltin.register('map', _do_map, EMap)
