from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject, AttrWhere
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin,
    get_guest_builtin,
)
from echo.interp_context import ICtx


class ETracebackType(EPyObject):
    def __repr__(self) -> Text:
        return "<eclass 'traceback'>"

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None


ETracebackType.singleton = ETracebackType()


class ETraceback(EPyObject):
    def __init__(self, data: Tuple[Text, ...]):
        self.data = data

    def get_type(self) -> EPyObject:
        return ETracebackType.singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name == 'tb_frame':
            return AttrWhere.SELF_SPECIAL
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == 'tb_frame':
            return Result(None)
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError
