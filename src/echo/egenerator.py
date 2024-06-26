from typing import Tuple, Any, Optional, Union

from echo.epy_object import EPyObject, AttrWhere, EPyType
from echo.interp_result import Result, ExceptionData
from echo.eobjects import EMethod, get_guest_builtin
from echo.return_kind import ReturnKind
from echo.interp_context import ICtx
from echo.value import Value
from echo.enative_fn import ENativeFn


class EGeneratorType(EPyType):
    def __init__(self):
        self._dict = {}

    def get_name(self) -> str:
        return 'generator'

    def __repr__(self) -> str:
        return "<eclass 'generator'>"

    def get_type(self) -> EPyType:
        return get_guest_builtin('type')

    def get_dict(self):
        raise NotImplementedError

    def get_bases(self):
        raise NotImplementedError

    def get_mro(self) -> Tuple[Union[EPyType, type], ...]:
        return (self, get_guest_builtin('object'))

    def getattr(self, name: str, ictx: ICtx) -> Result[Any]:
        if name == '__mro__':
            return Result(self.get_mro())
        if name == '__dict__':
            return Result(self._dict)
        raise NotImplementedError(self, name)

    def setattr(self, name: str, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: str) -> Optional[AttrWhere]:
        if name in ('__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        return None


EGeneratorType_singleton = EGeneratorType()


class EGenerator(EPyObject):
    def __init__(self, f):
        self.f = f

    def get_name(self) -> str:
        return 'generator'

    def get_type(self) -> EPyType:
        return EGeneratorType_singleton

    def _iter(self, args, kwargs, locals_dict, ictx,
              globals_=None) -> Result[EPyObject]:
        return Result(self)

    def hasattr_where(self, name: str) -> Optional[AttrWhere]:
        if name in ('__iter__', '__next__'):
            return AttrWhere.CLS
        raise NotImplementedError

    def getattr(self, name: str, ictx: ICtx) -> Result[Any]:
        if name == '__iter__':
            return Result(EMethod(ENativeFn(
                self._iter, 'egenerator.__iter__'), bound_self=self))
        if name == '__next__':
            return Result(EMethod(ENativeFn(
                self._next, 'egenerator.__next__'), bound_self=self))
        msg = f'Cannot find attribute {name} on {self}'
        return Result(ExceptionData(None, name, AttributeError(msg)))

    def setattr(self, name: str, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError

    def __next(self, ictx: ICtx) -> Result[Any]:
        result = self.f.run_to_return_or_yield()
        if result.is_exception():
            return Result(result.get_exception())

        v, return_kind = result.get_value()
        assert isinstance(v, Value), v
        if return_kind == ReturnKind.YIELD:
            return Result(v.wrapped)

        assert v.wrapped is None, v
        return Result(ExceptionData(None, None, StopIteration()))

    def _next(self, args, kwargs, locals_dict, ictx,
              globals_=None) -> Result[Any]:
        assert len(args) == 1 and not kwargs, (args, kwargs)
        assert args[0] is self
        return self.__next(ictx)
