from typing import Tuple, Any, Union, Optional

from echo.epy_object import EPyType, AttrWhere
from echo.eobjects import E_PREFIX, get_guest_builtin, EPyObject
from echo.interp_context import ICtx
from echo.interp_result import Result


StatefulFrame = Any


class EFrameType(EPyType):
    def __repr__(self) -> str:
        return f"<{E_PREFIX}class 'frame'>"

    def get_name(self) -> str:
        return 'frame'

    def get_dict(self):
        raise NotImplementedError

    def get_bases(self):
        raise NotImplementedError

    def get_mro(self) -> Tuple[Union[EPyType, type], ...]:
        return (self,)

    def get_type(self) -> EPyType:
        return get_guest_builtin('type')

    def hasattr_where(self, name: str) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: str, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: str, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError


EFrameType_singleton = EFrameType()


class EFrame(EPyObject):
    def __init__(self, frame: StatefulFrame):
        self.frame = frame

    @property
    def f_code(self):
        return self.frame.code

    @property
    def f_lineno(self):
        return self.frame.current_lineno

    @property
    def f_back(self) -> Optional['EFrame']:
        return (EFrame(self.frame.older_frame) if self.frame.older_frame
                else None)

    def __repr__(self) -> str:
        return (f'<frame, file {self.frame.code.co_filename!r}, '
                f'line {self.frame.current_lineno}, '
                f'code {self.frame.code.co_name}>')

    def get_type(self) -> EPyType:
        return EFrameType_singleton

    def hasattr_where(self, name: str) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: str, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: str, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError
