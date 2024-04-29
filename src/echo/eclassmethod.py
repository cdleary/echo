from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject, AttrWhere, EPyType
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EMethod, EBuiltin,
    get_guest_builtin, E_PREFIX,
)
from echo.enative_fn import ENativeFn
from echo.interp_context import ICtx


class EClassMethod(EPyObject):
    def __init__(self, f: EPyObject):
        self.f = f
        self.dict_: Dict[str, Any] = {}

    def __repr__(self) -> Text:
        return f'<{E_PREFIX}classmethod object at {id(self):#x}>'

    def get_type(self) -> EPyType:
        return get_guest_builtin('classmethod')

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
        _self, obj, objtype = args
        assert _self is self
        if obj is not None:
            do_type = get_guest_builtin('type')
            objtype = do_type.invoke((obj,), {}, {}, ictx).get_value()
        return Result(EMethod(self.f, bound_self=objtype))

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__get__':
            return Result(EMethod(ENativeFn(
                self._get, 'eclassmethod.__get__'), bound_self=self))
        if name == '__func__':
            return Result(self.f)
        if name in self.dict_:
            return Result(self.dict_[name])
        return Result(ExceptionData(
            None, None, AttributeError(name)))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        raise NotImplementedError(name, value)


@check_result
def _do_classmethod(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    assert isinstance(args[0], EPyObject), args[0]
    return Result(EClassMethod(args[0]))


EBuiltin.register('classmethod', _do_classmethod, EClassMethod)
