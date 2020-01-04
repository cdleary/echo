import os
from typing import Text, Tuple, Any, Dict, Optional

from echo.epy_object import EPyObject, AttrWhere
from echo.interp_result import Result, ExceptionData, check_result
from echo.eobjects import (
    EFunction, EMethod, NativeFunction, EBuiltin,
    get_guest_builtin,
)
from echo.interp_context import ICtx

E_PREFIX = 'e' if 'E_PREFIX' not in os.environ else os.environ['E_PREFIX']


class ETracebackType(EPyObject):
    def __repr__(self) -> Text:
        return f"<{E_PREFIX}class 'traceback'>"

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
    def __init__(self, frame: Any, lasti: int, lineno: int):
        self.frame = frame
        self.lasti = lasti
        self.lineno = lineno

    def __repr__(self) -> Text:
        return f'<{E_PREFIX}traceback object>'

    def get_type(self) -> EPyObject:
        return ETracebackType.singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('tb_frame', 'tb_lasti', 'tb_lineno'):
            return AttrWhere.SELF_SPECIAL
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == 'tb_frame':
            return Result(self.frame)
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


def walk(tb: ETraceback):
    frame = tb.frame
    while frame:
        yield frame.f_code.co_filename, frame.f_lineno
        frame = frame.f_back
