from typing import Text, Iterable, Dict, Any, Optional, Tuple

from echo.interp_context import ICtx
from echo.epy_object import EPyObject, EPyType, AttrWhere
from echo.eobjects import get_guest_builtin
from echo.interp_result import Result, ExceptionData


class EModuleType(EPyType):
    def __repr__(self) -> Text:
        return "<eclass 'module'>"

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def get_mro(self) -> Tuple[EPyObject, ...]:
        return (self,)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


EModuleType.singleton = EModuleType()


class EModule(EPyObject):
    def __init__(self, fully_qualified_name: Text, *, filename: Text,
                 globals_: Dict[Text, Any]):
        self.fully_qualified_name = fully_qualified_name
        self.filename = filename
        self.globals_ = globals_

    def __repr__(self) -> Text:
        return f'<module {self.fully_qualified_name!r} from {self.filename!r}>'

    def get_type(self) -> EPyObject:
        return EModuleType.singleton

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
            msg = (f'Module {self.fully_qualified_name} '
                   f'does not have attribute {name}')
            return Result(ExceptionData(None, None, AttributeError(msg)))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        assert not isinstance(value, Result), value
        self.globals_[name] = value
        return Result(None)
