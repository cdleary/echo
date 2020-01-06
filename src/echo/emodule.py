import os
from typing import Text, Iterable, Dict, Any, Optional, Tuple

from echo.interp_context import ICtx
from echo.epy_object import EPyObject, EPyType, AttrWhere
from echo.eobjects import get_guest_builtin
from echo.interp_result import Result, ExceptionData

E_PREFIX = 'e' if 'E_PREFIX' not in os.environ else os.environ['E_PREFIX']


class EModuleType(EPyType):
    def __repr__(self) -> Text:
        return f"<{E_PREFIX}class 'module'>"

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def get_dict(self):
        raise NotImplementedError

    def get_bases(self):
        raise NotImplementedError

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
                 globals_: Dict[Text, Any],
                 special_attrs: Dict[Text, Any] = {}):
        self.fully_qualified_name = fully_qualified_name
        self.filename = filename
        self.globals_ = globals_
        self.special_attrs = special_attrs

    def __repr__(self) -> Text:
        from_str = ('(built-in)' if self.filename == '<built-in>'
                    else f'from {self.filename!r}')
        return (f'<{E_PREFIX}module {self.fully_qualified_name!r} {from_str}>')

    def get_type(self) -> EPyObject:
        return EModuleType.singleton

    def keys(self) -> Iterable[Text]:
        return self.globals_.keys()

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__dict__',) + tuple(self.special_attrs.keys()):
            return AttrWhere.SELF_SPECIAL
        if name in self.globals_:
            return AttrWhere.SELF_SPECIAL
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__dict__':
            return Result(self.globals_)
        if name in self.special_attrs:
            return self.special_attrs[name][0](ictx)
        try:
            return Result(self.globals_[name])
        except KeyError:
            msg = (f'Module {self.fully_qualified_name} '
                   f'does not have attribute {name}')
            return Result(ExceptionData(None, None, AttributeError(msg)))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        assert not isinstance(value, Result), value
        if name in self.special_attrs:
            return self.special_attrs[name][1](value, ictx)
        self.globals_[name] = value
        return Result(None)
