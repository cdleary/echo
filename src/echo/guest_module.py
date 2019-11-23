from typing import Text, Iterable, Dict, Any

from echo.interp_context import ICtx
from echo.guest_py_object import GuestPyObject
from echo.interp_result import Result, ExceptionData


class GuestModule(GuestPyObject):
    def __init__(self, fully_qualified_name: Text, *, filename: Text,
                 globals_: Dict[Text, Any]):
        self.fully_qualified_name = fully_qualified_name
        self.filename = filename
        self.globals_ = globals_

    def __repr__(self) -> Text:
        return ('GuestModule(fully_qualified_name={!r}, '
                'filename={!r}, ...)'.format(
                    self.fully_qualified_name, self.filename))

    def keys(self) -> Iterable[Text]:
        return self.globals_.keys()

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__dict__':
            return Result(self.globals_)
        try:
            return Result(self.globals_[name])
        except KeyError:
            return Result(ExceptionData(None, name, AttributeError))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        assert not isinstance(value, Result), value
        self.globals_[name] = value
        return Result(None)
