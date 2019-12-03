from typing import Text, Iterable, Dict, Any, Optional

from echo.interp_context import ICtx
from echo.epy_object import EPyObject, AttrWhere
from echo.interp_result import Result, ExceptionData


class EModule(EPyObject):
    def __init__(self, fully_qualified_name: Text, *, filename: Text,
                 globals_: Dict[Text, Any]):
        self.fully_qualified_name = fully_qualified_name
        self.filename = filename
        self.globals_ = globals_

    def __repr__(self) -> Text:
        return ('EModule(fully_qualified_name={!r}, '
                'filename={!r}, ...)'.format(
                    self.fully_qualified_name, self.filename))

    def get_type(self) -> EPyObject:
        raise NotImplementedError

    def keys(self) -> Iterable[Text]:
        return self.globals_.keys()

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name == '__dict__':
            return AttrWhere.SELF_SPECIAL
        if name in self.globals_:
            return AttrWhere.SELF_SPECIAL
        return None

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
