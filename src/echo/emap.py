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
                self._get, 'eproperty.__get__'), bound_self=self))
        return Result(ExceptionData(None, name, AttributeError(name)))

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError


@check_result
def _do_map(
        args: Tuple[Any, ...],
        kwargs: Optional[Dict[Text, Any]],
        ictx: ICtx) -> Result[Any]:
    if kwargs:
        raise NotImplementedError(kwargs)
    if len(args) != 2:
        raise NotImplementedError(args)
    e = EMap(args[0], args[1])
    return Result(e)


EBuiltin.register('map', _do_map, EMap)
