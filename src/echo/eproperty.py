from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject
from echo.interp_result import Result, ExceptionData, check_result
from echo.guest_objects import EFunction, EMethod, NativeFunction, EBuiltin
from echo.interp_context import ICtx


class EProperty(EPyObject):
    def __init__(self, fget: EFunction):
        self.fget = fget

    def hasattr(self, name: Text) -> bool:
        return name in ('__get__', '__set__')

    @check_result
    def _get(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
        _self, obj, objtype = args
        assert _self is self
        return self.fget.invoke((obj,), kwargs, locals_dict, ictx)

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__get__':
            return Result(EMethod(NativeFunction(
                self._get, 'eproperty.__get__'), bound_self=self))
        return Result(ExceptionData(None, name, AttributeError))

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError


@check_result
def _do_property(
        args: Tuple[Any, ...],
        kwargs: Optional[Dict[Text, Any]],
        ictx: ICtx) -> Result[Any]:
    if kwargs:
        raise NotImplementedError(kwargs)
    if len(args) != 1:
        raise NotImplementedError(args)
    guest_property = EProperty(args[0])
    return Result(guest_property)


EBuiltin.register('property', _do_property)
