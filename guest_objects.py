import abc
import types
from typing import Text, Any, Dict, Iterable, Tuple, Optional

from interp_result import Result, ExceptionData


class GuestPyObject:

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def getattr(self, name: Text) -> Any:
        raise NotImplementedError(self, name)

    @abc.abstractmethod
    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


class GuestModule(GuestPyObject):
    def __init__(self, name: Text, *, filename: Text, code: types.CodeType,
                 globals_: Dict[Text, Any]):
        self.name = name
        self.filename = filename
        self.code = code
        self.globals_ = globals_

    def __repr__(self):
        return 'GuestModule(name={!r}, filename={!r}, ...)'.format(
            self.name, self.filename)

    def keys(self) -> Iterable[Text]:
        return self.globals_.keys()

    def getattr(self, name: Text) -> Any:
        return self.globals_[name]

    def setattr(self, name: Text, value: Any):
        assert not isinstance(value, Result), value
        self.globals_[name] = value


class GuestFunction(GuestPyObject):
    def __init__(self, code, globals_, name, *, defaults=None,
                 kwarg_defaults: Optional[Dict[Text, Any]] = None,
                 closure=None):
        self.code = code
        self.globals_ = globals_
        self.name = name
        self.defaults = defaults
        self.kwarg_defaults = kwarg_defaults
        self.closure = closure

    def __repr__(self):
        return ('GuestFunction(code={!r}, name={!r}, closure={!r}, '
                'defaults={!r}, kwarg_defaults={!r})').format(
                    self.code, self.name, self.closure, self.defaults,
                    self.kwarg_defaults)

    def invoke(self, args: Tuple[Any, ...], interp) -> Result[Any]:
        return interp(self.code, globals_=self.globals_, args=args,
                      defaults=self.defaults,
                      kwarg_defaults=self.kwarg_defaults, closure=self.closure,
                      in_function=True)

    def getattr(self, name: Text) -> Any:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestInstance(GuestPyObject):

    def __init__(self, cls: 'GuestClass'):
        self.cls = cls
        self.dict = {}

    def getattr(self, name: Text) -> Any:
        return self.dict[name]

    def setattr(self, name: Text, value: Any):
        self.dict[name] = value


class GuestClass(GuestPyObject):
    def __init__(self, name, dict_, bases=None, metaclass=None, kwargs=None):
        self.name = name
        self.dict_ = dict_
        self.bases = bases or ()
        self.metaclass = metaclass
        self.kwargs = kwargs

    def __repr__(self) -> Text:
        return 'GuestClass(name={!r}, ...)'.format(self.name)

    def instantiate(self, args: Tuple[Any, ...], do_call,
                    globals_: Dict[Text, Any]) -> Result[GuestInstance]:
        guest_instance = GuestInstance(self)
        if '__init__' in self.dict_:
            init_f = self.dict_['__init__']
            # TODO(cdleary, 2019-01-26) What does Python do when you return
            # something non-None from initializer? Ignore?
            result = do_call(init_f, args=(guest_instance,) + args,
                             globals_=globals_)
            if result.is_exception():
                return result
        return Result(guest_instance)

    def getattr(self, name: Text) -> Any:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


def _do_isinstance(args: Tuple[Any, ...]) -> Result[bool]:
    assert len(args) == 2, args
    if args[1] is int:
        return Result(isinstance(args[0], int))
    if args[1] is str:
        return Result(isinstance(args[0], str))
    if args[1] is type:
        return Result(isinstance(args[0], (type, GuestClass)))
    raise NotImplementedError(args)


def _do_issubclass(args: Tuple[Any, ...]) -> Result[bool]:
    # TODO(cdleary, 2019-02-10): Detect "guest" subclass relations.
    assert len(args) == 2, args
    return Result(issubclass(args[0], args[1]))


class GuestBuiltin(GuestPyObject):
    def __init__(self, name: Text, bound_self: Any):
        self.name = name
        self.bound_self = bound_self

    def __repr__(self):
        return 'GuestBuiltin(name={!r}, ...)'.format(self.name)

    def invoke(self, args: Tuple[Any, ...], interp) -> Result[Any]:
        if self.name == 'dict.keys':
            assert not args, args
            return Result(self.bound_self.keys())
        if self.name == 'list.append':
            return Result(self.bound_self.append(*args))
        if self.name == 'list.insert':
            return Result(self.bound_self.insert(*args))
        if self.name == 'list.remove':
            try:
                return Result(self.bound_self.remove(*args))
            except ValueError as e:
                return Result(ExceptionData(traceback=None, parameter=e.args,
                                            exception=ValueError))
        if self.name == 'isinstance':
            return _do_isinstance(args)
        elif self.name == 'issubclass':
            return _do_issubclass(args)
        else:
            raise NotImplementedError(self.name)

    def getattr(self, name: Text) -> Any:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestPartial(object):
    def __init__(self, f: GuestFunction, args: Tuple[Any, ...]):
        assert isinstance(f, GuestFunction), f
        self.f = f
        self.args = args

    def invoke(self, args: Tuple[Any, ...], interp) -> Any:
        return self.f.invoke(self.args + args, interp=interp)
