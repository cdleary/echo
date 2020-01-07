from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject, AttrWhere
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin,
    get_guest_builtin, E_PREFIX,
)
from echo.interp_context import ICtx


class EStaticMethod(EPyObject):
    def __init__(self, f: EPyObject):
        self.f = f
        self.dict_ = {}

    def __repr__(self) -> Text:
        return f'<{E_PREFIX}staticmethod object at {id(self):#x}>'

    def get_type(self) -> EPyObject:
        return get_guest_builtin('staticmethod')

    def invoke(self, *args, **kwargs) -> Result[Any]:
        return self.f.invoke(*args, **kwargs)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict_:
            return AttrWhere.SELF_DICT
        if name == '__func__':
            return AttrWhere.SELF_SPECIAL
        if name == '__get__':
            return AttrWhere.CLS
        return None

    @check_result
    def _get(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx,
             globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        return Result(self.f)

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__get__':
            return Result(NativeFunction(
                self._get, 'estaticmethod.__get__'))
        if name == '__func__':
            return Result(self.f)
        raise NotImplementedError(name)

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError(name, value)


@check_result
def _do_staticmethod(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    assert isinstance(args[0], EPyObject), args[0]
    return Result(EStaticMethod(args[0]))


EBuiltin.register('staticmethod', _do_staticmethod, EStaticMethod)
