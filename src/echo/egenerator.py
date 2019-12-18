from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject, AttrWhere, EPyType
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin,
    get_guest_builtin,
)
from echo.return_kind import ReturnKind
from echo.interp_context import ICtx
from echo.value import Value


class EGeneratorType(EPyType):
    def __init__(self):
        self._dict = {}

    def __repr__(self) -> Text:
        return "<eclass 'generator'>"

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


EGeneratorType.singleton = EGeneratorType()


class EGenerator(EPyObject):
    def __init__(self, f):
        self.f = f

    def get_type(self) -> EPyObject:
        return EGeneratorType.singleton

    def _iter(self, args, kwargs, locals_dict, ictx) -> Result[EPyObject]:
        return Result(self)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name == '__iter__':
            return AttrWhere.CLS
        raise NotImplementedError

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__iter__':
            return Result(EMethod(NativeFunction(
                self._iter, 'egenerator.__iter__'), bound_self=self))
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

    def next(self, ictx: ICtx) -> Result[Value]:
        result = self.f.run_to_return_or_yield()
        if result.is_exception():
            return Result(result.get_exception())

        v, return_kind = result.get_value()
        assert isinstance(v, Value), v
        if return_kind == ReturnKind.YIELD:
            return Result(v.wrapped)

        assert v.wrapped is None, v
        return Result(ExceptionData(None, None, StopIteration()))
