from typing import Callable, Optional, Any

from echo.epy_object import EPyObject, EPyType, AttrWhere
from echo.interp_result import Result, check_result
from echo.interp_context import ICtx
from echo import eobjects


class ENativeFn(EPyObject):

    def __init__(self, f: Callable[..., Result], name: str):
        self.f = f
        self.name = name

    def __repr__(self) -> str:
        return f'<built-in function {self.name}>'

    def get_type(self) -> EPyType:
        return eobjects.EFunctionType.get_singleton()

    def hasattr_where(self, name: str) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: str, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: str, value: Any, ictx: ICtx) -> Result[None]:
        raise NotImplementedError

    @check_result
    def invoke(self, *args, **kwargs) -> Result[Any]:
        return self.f(*args, **kwargs)
