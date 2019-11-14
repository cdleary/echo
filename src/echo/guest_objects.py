import abc
import collections
import itertools
import os
import pprint
import sys
import types
from typing import (
    Text, Any, Dict, Iterable, Tuple, Optional, Set, Callable, Union,
)
from enum import Enum
import weakref

from echo.interpreter_state import InterpreterState
from echo.code_attributes import CodeAttributes
from echo.interp_result import Result, ExceptionData, check_result
from echo.value import Value
from echo.common import memoize


DEBUG_PRINT_BYTECODE = bool(os.getenv('DEBUG_PRINT_BYTECODE', False))


class ReturnKind(Enum):
    RETURN = 'return'
    YIELD = 'yield'


class GuestPyObject(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        raise NotImplementedError(self, name)

    @abc.abstractmethod
    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)

    def hasattr(self, name: Text) -> bool:
        raise NotImplementedError(self, name)

    # @abc.abstractmethod
    def delattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


class GuestModule(GuestPyObject):
    def __init__(self, fully_qualified_name: Text, *, filename: Text,
                 globals_: Dict[Text, Any]):
        self.fully_qualified_name = fully_qualified_name
        self.filename = filename
        self.globals_ = globals_

    def __repr__(self):
        return ('GuestModule(fully_qualified_name={!r}, '
                'filename={!r}, ...)'.format(
                    self.fully_qualified_name, self.filename))

    def keys(self) -> Iterable[Text]:
        return self.globals_.keys()

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name == '__dict__':
            return Result(self.globals_)
        try:
            return Result(self.globals_[name])
        except KeyError:
            return Result(ExceptionData(None, name, AttributeError))

    def setattr(self, name: Text, value: Any,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[None]:
        assert not isinstance(value, Result), value
        self.globals_[name] = value
        return Result(None)


class GuestFunction(GuestPyObject):
    def __init__(self, code: types.CodeType, globals_, name, *, defaults=None,
                 kwarg_defaults: Optional[Dict[Text, Any]] = None,
                 closure=None):
        self.code = code
        self._code_attrs = CodeAttributes.from_code(code, name=name)
        self.globals_ = globals_
        self.name = name
        self.defaults = defaults
        self.kwarg_defaults = kwarg_defaults
        self.closure = closure
        self.dict_ = {
            '__code__': code,
        }

    def __repr__(self):
        return '<efunction {} at {:#x}>'.format(self.name, id(self))

    @check_result
    def invoke(self, *, args: Tuple[Any, ...],
               interp_callback: Callable,
               interp_state: InterpreterState,
               kwargs: Optional[Dict[Text, Any]] = None,
               locals_dict: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        if self._code_attrs.coroutine:
            return Result(GuestCoroutine(self))

        return interp_callback(
            self.code, globals_=self.globals_, args=args, kwargs=kwargs,
            defaults=self.defaults, locals_dict=locals_dict, name=self.name,
            kwarg_defaults=self.kwarg_defaults, closure=self.closure)

    def hasattr(self, name: Text) -> bool:
        return name in self.dict_ or name in ('__get__', '__class__')

    def _get(self, args, *,
             interp_callback: Callable,
             interp_state: InterpreterState,
             ) -> Result[Any]:
        _self, obj, objtype = args
        assert self is _self
        if obj is None:
            return Result(_self)
        return Result(GuestMethod(f=_self, bound_self=obj))

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name == '__class__':
            return Result(GuestFunctionType.singleton)
        if name == '__get__':
            return Result(GuestMethod(NativeFunction(
                self._get, 'efunction.__get__'), bound_self=self))
        try:
            return Result(self.dict_[name])
        except KeyError:
            return Result(ExceptionData(None, name, AttributeError))

    def setattr(self, name: Text, value: Any,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[None]:
        self.dict_[name] = value
        return Result(None)


class GuestCoroutine(GuestPyObject):
    def __init__(self, f: GuestFunction):
        self.f = f

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name == 'close':
            def fake(x): pass
            guest_f = GuestFunction(
                getattr(fake, '__code__'), {}, 'coroutine.close')
            guest_m = GuestMethod(guest_f, self)
            return Result(guest_m)
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestAsyncGenerator(GuestPyObject):
    def __init__(self, f):
        self.f = f

    def getattr(self, name: Text) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestTraceback(GuestPyObject):
    def __init__(self, data: Tuple[Text, ...]):
        self.data = data

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name == 'tb_frame':
            return Result(None)
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class GuestGenerator(GuestPyObject):
    def __init__(self, f):
        self.f = f

    def getattr(self, name: Text) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

    def next(self) -> Result[Value]:
        result = self.f.run_to_return_or_yield()
        if result.is_exception():
            return Result(result.get_exception())

        v, return_kind = result.get_value()
        assert isinstance(v, Value), v
        if return_kind == ReturnKind.YIELD:
            return Result(v.wrapped)

        assert v.wrapped is None, v
        return Result(ExceptionData(None, None, StopIteration))


class GuestMethod(GuestPyObject):

    def __init__(self, f: Union[GuestFunction, 'NativeFunction'], bound_self):
        self.f = f
        self.bound_self = bound_self

    def __repr__(self) -> Text:
        return '<ebound method {} of {!r}>'.format(
            self.f.name, self.bound_self)

    @property
    def code(self): return self.f.code

    @property
    def globals_(self): return self.f.globals_

    @property
    def name(self): return self.f.name

    @property
    def defaults(self): return self.f.defaults

    @property
    def kwarg_defaults(self): return self.f.kwarg_defaults

    @property
    def closure(self): return self.f.closure

    def hasattr(self, name: Text) -> bool:
        return name in ('__self__', '__func__') or self.f.hasattr(name)

    def getattr(self, name: Text, *args, **kwargs) -> Result[Any]:
        if name == '__self__':
            return Result(self.bound_self)
        if name == '__func__':
            return Result(self.f)
        return self.f.getattr(name, *args, **kwargs)

    def setattr(self, *args, **kwargs):
        return self.f.setattr(*args, **kwargs)

    @check_result
    def invoke(self, *, args: Tuple[Any, ...],
               interp_callback: Callable,
               interp_state: InterpreterState,
               kwargs: Optional[Dict[Text, Any]] = None,
               locals_dict=None) -> Result[Any]:
        return self.f.invoke(
            args=(self.bound_self,) + args, kwargs=kwargs,
            interp_state=interp_state, locals_dict=locals_dict,
            interp_callback=interp_callback)


@check_result
def _invoke_desc(
        self, cls_attr,
        *,
        interp_state: InterpreterState,
        interp_callback: Optional[Callable] = None,
        ) -> Result[Any]:
    assert cls_attr.hasattr('__get__')
    f_result = cls_attr.getattr('__get__', interp_state=interp_state,
                                interp_callback=interp_callback)
    if f_result.is_exception():
        return Result(f_result.get_exception())
    objtype_result = _do_type(args=(cls_attr,))
    if objtype_result.is_exception():
        return Result(objtype_result.get_exception())
    objtype = objtype_result.get_value()
    return f_result.get_value().invoke(
        args=(self, objtype), interp_callback=interp_callback,
        interp_state=interp_state)


class GuestInstance(GuestPyObject):

    def __init__(self, cls: Union['GuestClass', 'GuestBuiltin']):
        assert isinstance(cls, (GuestClass, GuestBuiltin)), cls
        self.cls = cls
        self.dict_ = {}

    def __repr__(self) -> Text:
        return '<{} object>'.format(self.cls.name)

    def get_type(self) -> Union['GuestClass', 'GuestBuiltin']:
        return self.cls

    def hasattr(self, name: Text) -> bool:
        if name in self.dict_:
            return True
        # Special members.
        if name in ('__class__',):
            return True
        cls_hasattr = self.cls.hasattr(name)
        assert isinstance(cls_hasattr, bool), (self.cls, cls_hasattr)
        return cls_hasattr

    def _search_mro_for(self, name: Text) -> Optional[Any]:
        for cls in self.cls.get_mro():
            if not isinstance(cls, GuestClass):
                continue
            if name in cls.dict_:
                return cls.dict_[name]
        return None

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        cls_attr = self._search_mro_for(name)

        if DEBUG_PRINT_BYTECODE:
            print('[go:gi:ga] self:', self, 'name:', name, 'cls_attr:', cls_attr, file=sys.stderr)

        if (isinstance(cls_attr, GuestInstance)
                and cls_attr.hasattr('__get__')
                and cls_attr.hasattr('__set__')):
            if DEBUG_PRINT_BYTECODE:
                print('[go:gi:ga] overriding descriptor:', cls_attr, file=sys.stderr)
            # Overriding descriptor.
            return _invoke_desc(self, cls_attr, interp_state=interp_state,
                                interp_callback=interp_callback)

        try:
            return Result(self.dict_[name])
        except KeyError:
            if name == '__class__':
                return Result(self.cls)
            if name == '__dict__':
                return Result(self.dict_)

        if isinstance(cls_attr, GuestPyObject) and cls_attr.hasattr('__get__'):
            if DEBUG_PRINT_BYTECODE:
                print('[go:gi:ga] non-overriding descriptor:', cls_attr, file=sys.stderr)
            return _invoke_desc(self, cls_attr, interp_state=interp_state,
                                interp_callback=interp_callback)

        if cls_attr is not None:
            return Result(cls_attr)

        return Result(ExceptionData(
            None,
            f"'{self.cls.name}' object does not have attribute {name!r}",
            AttributeError))

    @check_result
    def setattr(self, name: Text, value: Any,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[None]:
        cls_attr = None
        if name in self.cls.dict_:
            cls_attr = self.cls.dict_[name]

        if (isinstance(cls_attr, GuestInstance)
                and cls_attr.hasattr('__set__')):
            f_result = cls_attr.getattr('__set__', interp_state=interp_state,
                                        interp_callback=interp_callback)
            if f_result.is_exception():
                return Result(f_result.get_exception())
            return f_result.get_value().invoke(
                args=(self, value), interp_callback=interp_callback,
                interp_state=interp_state)

        self.dict_[name] = value
        return Result(None)


GuestClassOrBuiltin = Union['GuestClass', 'GuestBuiltin']


def get_bases(c: GuestClassOrBuiltin) -> Tuple[GuestPyObject, ...]:
    if isinstance(c, GuestClass):
        return c.bases
    if _is_type_builtin(c):
        return (get_guest_builtin('object'),)
    if _is_object_builtin(c):
        return ()
    raise NotImplementedError(c)


class GuestClass(GuestPyObject):
    bases: Tuple[GuestClassOrBuiltin, ...]
    metaclass: Optional[GuestClassOrBuiltin]
    subclasses: Set['GuestClass']

    def __init__(self, name: Text, dict_: Dict[Text, Any], *,
                 bases: Optional[Tuple[GuestClassOrBuiltin]] = None,
                 metaclass=None, kwargs=None):
        self.name = name
        self.dict_ = dict_
        self.bases = bases or ()
        self.metaclass = metaclass
        self.kwargs = kwargs
        self.subclasses = weakref.WeakSet()

        for base in self.bases:
            if isinstance(base, (GuestBuiltin, GuestClass)):
                base.note_subclass(self)

    def note_subclass(self, derived: 'GuestClass') -> None:
        self.subclasses.add(derived)

    def __repr__(self) -> Text:
        return '<eclass \'{}.{}\'>'.format(self.dict_['__module__'], self.name)

    def get_type(self) -> 'GuestClass':
        return self.metaclass or get_guest_builtin('type')

    def get_mro(self) -> Tuple['GuestPyObject', ...]:
        """The MRO is a preorder DFS of the 'derives from' relation."""
        derives_from = []  # (cls, base)
        frontier = collections.deque([self])
        while frontier:
            cls = frontier.popleft()
            for base in get_bases(cls):
                derives_from.append((cls, base))
                frontier.append(base)

        cls_to_subclasses = collections.defaultdict(list)
        for cls, base in derives_from:
            cls_to_subclasses[base].append(cls)
        cls_to_subclasses = dict(cls_to_subclasses)

        ready = collections.deque([self])
        order = []

        def is_ready(c) -> bool:
            return all(sc in order for sc in cls_to_subclasses.get(c, []))

        assert is_ready(self)

        while ready:
            c = ready.popleft()
            order.append(c)
            for b in reversed(get_bases(c)):
                if is_ready(b):
                    ready.appendleft(b)

        order.append(get_guest_builtin('object'))
        return tuple(order)

    def is_subtype_of(self, other: 'GuestClass') -> bool:
        if self is other:
            return True
        return other in self.get_mro()

    def is_strict_subtype_of(self, other: 'GuestClass') -> bool:
        if self is other:
            return False
        return self.is_subtype_of(other)

    def instantiate(self, args: Tuple[Any, ...], *,
                    interp_state: InterpreterState,
                    interp_callback: Callable,
                    do_call: Callable,
                    globals_: Dict[Text, Any]) -> Result[GuestInstance]:
        if DEBUG_PRINT_BYTECODE:
            print(f'[go:gc] instantiate args: {args}', file=sys.stderr)
        guest_instance = None
        if self.hasattr('__new__'):
            new_f = self.getattr(
                '__new__', interp_state=interp_state).get_value()
            result = do_call(new_f, args=(self,) + args, globals_=globals_)
            if result.is_exception():
                return Result(result.get_exception())
            guest_instance = result.get_value()
            if not _do_isinstance(args=(guest_instance, self), call=do_call,
                                  interp_state=interp_state,
                                  interp_callback=interp_callback).get_value():
                return Result(guest_instance)
        guest_instance = guest_instance or GuestInstance(self)
        if self.hasattr('__init__'):
            init_f = self.getattr(
                '__init__', interp_state=interp_state).get_value()
            # TODO(cdleary, 2019-01-26) What does Python do when you return
            # something non-None from initializer? Ignore?
            assert isinstance(guest_instance, GuestPyObject), guest_instance
            result = do_call(init_f, args=(guest_instance,) + args,
                             globals_=globals_)
            if result.is_exception():
                return result
        return Result(guest_instance)

    def hasattr(self, name: Text) -> bool:
        if name in self.dict_:
            return True
        if name in ('__class__', '__bases__', '__subclasses__', '__mro__'):
            return True
        if any(base.hasattr(name) for base in self.bases):
            return True
        if self.metaclass and self.metaclass.hasattr(name):
            return True
        return False

    @check_result
    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name == '__dict__':
            return Result(self.dict_)

        if name in self.dict_:
            v = self.dict_[name]
            if isinstance(v, GuestPyObject) and v.hasattr('__get__'):
                f_result = v.getattr('__get__', interp_state=interp_state,
                                            interp_callback=interp_callback)
                if f_result.is_exception():
                    return Result(f_result.get_exception())
                return f_result.get_value().invoke(
                    args=(None, self), interp_callback=interp_callback,
                    interp_state=interp_state)
            return Result(v)

        if name == '__mro__':
            return Result(self.get_mro())
        if name == '__class__':
            return Result(self.metaclass or get_guest_builtin('type'))
        if name == '__bases__':
            return Result(self.bases)
        if name == '__subclasses__':
            return Result(get_guest_builtin('type.__subclasses__'))
        if DEBUG_PRINT_BYTECODE:
            print('[go:ga] bases:', self.bases, 'metaclass:',
                  self.metaclass)
        for base in self.bases:
            if base.hasattr(name):
                return base.getattr(name, interp_state=interp_state,
                                    interp_callback=interp_callback)
        if self.metaclass:
            if self.metaclass.hasattr(name):
                return self.metaclass.getattr(
                    name, interp_state=interp_state,
                    interp_callback=interp_callback)
        return Result(ExceptionData(
            None,
            f'Class {self.name} does not have attribute {name!r}',
            AttributeError))

    def setattr(self, name: Text, value: Any,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[None]:
        self.dict_[name] = value
        return Result(None)


class GuestFunctionType(GuestPyObject):
    name = 'efunction'

    def hasattr(self, name: Text) -> bool:
        return name in ('__code__', '__globals__', '__get__')

    def _get_desc(self, args, *,
             interp_callback: Callable,
             interp_state: InterpreterState,
             ) -> Result[Any]:
        self, obj, objtype = args
        if obj is None:
            return Result(self)
        return Result(GuestMethod(self, bound_self=obj))

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Callable,
                ) -> Result[Any]:
        if name in ('__code__', '__globals__'):
            return Result(None)

        if name == '__get__':
            return Result(NativeFunction(self._get_desc, 'efunction.__get__'))

        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


GuestFunctionType.singleton = GuestFunctionType()


class GuestCoroutineType(GuestPyObject):

    def hasattr(self, name: Text) -> bool:
        return False

    def getattr(self, name: Text) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


def _is_type_builtin(x) -> bool:
    return isinstance(x, GuestBuiltin) and x.name == 'type'


def _is_object_builtin(x) -> bool:
    return isinstance(x, GuestBuiltin) and x.name == 'object'


def _is_str_builtin(x) -> bool:
    return isinstance(x, GuestBuiltin) and x.name == 'str'


def _do_isinstance(
        args: Tuple[Any, ...],
        call: Callable, *,
        interp_state: InterpreterState,
        interp_callback: Callable) -> Result[bool]:
    assert len(args) == 2, args

    if (isinstance(args[1], GuestClass) and
            args[1].hasattr('__instancecheck__')):
        ic = args[1].getattr('__instancecheck__', interp_state=interp_state,
                             interp_callback=interp_callback)
        if ic.is_exception():
            return Result(ic.get_exception())
        ic = ic.get_value()
        result = call(ic, args=(args[1], args[0]), globals_=ic.globals_)
        return result

    for t in (bool, int, str, float, dict, list, tuple, set):
        if args[1] is t:
            return Result(isinstance(args[0], t))

    if args[1] is type:
        return Result(isinstance(args[0], (type, GuestClass)))

    if isinstance(args[1], type) and issubclass(args[1], Exception):
        # TODO(leary) How does the real type builtin make it here?
        return Result(isinstance(args[0], args[1]))

    if _is_type_builtin(args[1]):
        if _is_type_builtin(args[0]) or _is_object_builtin(args[0]):
            return Result(True)
        type_types = (type, GuestClass, GuestFunctionType, GuestCoroutineType)
        return Result(isinstance(args[0], type_types))

    if _is_str_builtin(args[1]):
        return Result(isinstance(args[0], str))

    if args[0] is None:
        return Result(args[1] is type(None))  # noqa

    if _is_object_builtin(args[1]):
        return Result(True)  # Everything is an object.

    if (not isinstance(args[0], GuestPyObject)
            and isinstance(args[1], GuestClass)):
        return Result(type(args[0]) in args[1].get_mro())

    if isinstance(args[0], GuestPyObject) and isinstance(args[1], GuestClass):
        return Result(args[0].get_type() in args[1].get_mro())

    raise NotImplementedError(args)


def _do_issubclass(
        args: Tuple[Any, ...],
        call: Callable, *,
        interp_state: InterpreterState,
        interp_callback: Callable) -> Result[bool]:
    # TODO(cdleary, 2019-02-10): Detect "guest" subclass relations.
    assert len(args) == 2, args
    if DEBUG_PRINT_BYTECODE:
        print('[go:issubclass] arg0:', args[0], file=sys.stderr)
        print('[go:issubclass] arg1:', args[1], file=sys.stderr)

    if (isinstance(args[1], GuestPyObject) and
            args[1].hasattr('__subclasscheck__')):
        scc = args[1].getattr('__subclasscheck__', interp_state=interp_state,
                              interp_callback=interp_callback)
        if scc.is_exception():
            return Result(scc.get_exception())
        scc = scc.get_value()
        result = call(scc, args=(args[0],), globals_=scc.globals_)
        return result

    if isinstance(args[0], GuestClass) and isinstance(args[1], GuestClass):
        return Result(args[0].is_subtype_of(args[1]))

    if isinstance(args[0], GuestCoroutineType):
        return Result(_is_type_builtin(args[1]))

    if _is_object_builtin(args[0]) and _is_type_builtin(args[1]):
        return Result(False)
    if _is_object_builtin(args[1]):
        return Result(True)

    if not isinstance(args[1], type):
        raise NotImplementedError(args)

    if isinstance(args[0], GuestClass):
        return Result(args[1] in args[0].get_mro())

    return Result(issubclass(args[0], args[1]))


def _do_next(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 1, args
    g = args[0]
    assert isinstance(g, GuestGenerator), g
    return g.next()


def _do_hasattr(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 2, args
    o, attr = args
    if not isinstance(o, GuestPyObject):
        return Result(hasattr(o, attr))
    assert isinstance(attr, str), attr
    b = o.hasattr(attr)
    assert isinstance(b, bool), b
    return Result(b)


def _do_repr(args: Tuple[Any, ...], do_call) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if not isinstance(o, GuestPyObject):
        return Result(repr(o))
    frepr = o.getattr('__repr__')
    if frepr.is_exception():
        return frepr
    frepr = frepr.get_value()
    globals_ = frepr.getattr('__globals__')
    return do_call(frepr, args=(), globals_=globals_)


def _do_str(args: Tuple[Any, ...], do_call) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if not isinstance(o, GuestPyObject):
        return Result(repr(o))
    frepr = o.getattr('__str__')
    if frepr.is_exception():
        return frepr
    frepr = frepr.get_value()
    globals_ = frepr.getattr('__globals__')
    return do_call(frepr, args=(), globals_=globals_)


def _do_object(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 0, args
    return Result(GuestInstance(cls=get_guest_builtin('object')))


def _do_type_new(
        args: Tuple[Any, ...],
        *,
        interp_state: InterpreterState,
        interp_callback: Callable,
        kwargs: Optional[Dict[Text, Any]] = None,
        call: Callable) -> Result[GuestClass]:
    if kwargs:
        kwarg_metaclass = kwargs.pop('metaclass', args[0])
        assert kwarg_metaclass is args[0]
        assert not kwargs, kwargs
    metaclass, name, bases, ns = args
    cls = GuestClass(name, dict_=ns, bases=bases, metaclass=metaclass)
    return Result(cls)


def _do_type_subclasses(
        args: Tuple[Any, ...],
        *,
        interp_state: InterpreterState,
        interp_callback: Callable,
        kwargs: Optional[Dict[Text, Any]] = None,
        call: Callable) -> Result[GuestClass]:
    assert len(args) == 1, args
    c = args[0]
    assert isinstance(c, GuestClass), c
    return Result(sorted(list(c.subclasses)))


def _do_object_subclasshook(
        args: Tuple[Any, ...],
        *,
        interp_state: InterpreterState,
        interp_callback: Callable,
        kwargs: Optional[Dict[Text, Any]] = None,
        call: Callable) -> Result[GuestClass]:
    return Result(NotImplemented)


def _do_dir(args: Tuple[Any, ...], do_call, *,
            interp_callback: Callable,
            interp_state: InterpreterState) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if isinstance(o, GuestPyObject):
        d = o.getattr('__dict__', interp_state=interp_state,
                      interp_callback=interp_callback)
        if d.is_exception():
            return d.get_exception()
        d = d.get_value()
        keys = set(d.keys())
        keys.add('__class__')
        keys.add('__dict__')
        if isinstance(o, GuestInstance):
            result = _do_dir(
                (o.cls,), do_call, interp_callback=interp_callback,
                interp_state=interp_state)
            if result.is_exception():
                return Result(result.get_exception())
            assert isinstance(result.get_value(), list), result
            keys |= set(result.get_value())
        return Result(sorted(list(keys)))
    return Result(dir(o))


def _do_type(args: Tuple[Any, ...]) -> Result[Any]:
    if len(args) == 1:
        if DEBUG_PRINT_BYTECODE:
            print('[go:type]', args, file=sys.stderr)
        if isinstance(args[0], (GuestInstance, GuestSuper)):
            return Result(args[0].get_type())
        if isinstance(args[0], GuestClass):
            return Result(args[0].metaclass or get_guest_builtin('type'))
        if isinstance(args[0], GuestFunction):
            return Result(GuestFunctionType.singleton)
        if isinstance(args[0], GuestCoroutine):
            return Result(GuestCoroutineType())
        if isinstance(args[0], GuestClassMethod):
            return Result(classmethod)
        if _is_type_builtin(args[0]):
            return Result(args[0])
        res = type(args[0])
        if res is object:
            return Result(get_guest_builtin('object'))
        if res is type:
            return Result(get_guest_builtin('type'))
        return Result(res)
    assert len(args) == 3, args
    name, bases, ns = args

    cls = GuestClass(name, ns, bases=bases)

    if '__classcell__' in ns:
        ns['__classcell__'].set(cls)
        del ns['__classcell__']

    return Result(cls)



@check_result
def _do___build_class__(
        args: Tuple[Any, ...],
        *,
        interp_state: InterpreterState,
        interp_callback: Callable,
        kwargs: Optional[Dict[Text, Any]] = None,
        call: Callable) -> Result[GuestClass]:
    if DEBUG_PRINT_BYTECODE:
        print('[go:bc]', args)
    func, name, *bases = args
    bases = tuple(bases)
    ns = {}  # Namespace for the class.
    class_eval_result = call(func, args=(), locals_dict=ns,
                             globals_=func.globals_)
    if class_eval_result.is_exception():
        return Result(class_eval_result.get_exception())
    cell = class_eval_result.get_value()
    metaclass = kwargs.pop('metaclass', None) if kwargs else None
    if cell is None:
        ns['__module__'] = func.globals_['__name__']
        if metaclass and metaclass.hasattr('__new__'):
            new_f = metaclass.getattr(
                '__new__', interp_state=interp_state,
                interp_callback=interp_callback).get_value()
            return call(new_f,
                        args=(metaclass, name, bases, ns), kwargs=kwargs,
                        globals_=new_f.globals_)
        return Result(GuestClass(name, ns, bases=bases, metaclass=metaclass))

    if metaclass:
        raise NotImplementedError(metaclass, cell)

    # Now we call the metaclass with the evaluated namespace.
    cls_result = _do_type(args=(name, bases, ns))
    if cls_result.is_exception():
        return Result(cls_result.get_exception())

    # TODO(cdleary, 2019-02-16): Various checks that cell's class matches class
    # object.

    return cls_result


def get_mro(o: GuestPyObject):
    if _is_type_builtin(o):
        return (get_guest_builtin('type'), get_guest_builtin('object'))
    assert isinstance(o, GuestClass), o
    return o.get_mro()


class GuestSuper(GuestPyObject):
    def __init__(self, type_, obj_or_type, obj_or_type_type):
        self.type_ = type_
        self.obj_or_type = obj_or_type
        self.obj_or_type_type = obj_or_type_type

    def get_type(self) -> 'GuestPyObject':
        return get_guest_builtin('super')

    def __repr__(self) -> Text:
        return "<esuper: <class '{}'>, <{} object>>".format(
            self.type_.name, self.obj_or_type_type.name)

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name == '__thisclass__':
            return Result(self.type_)
        if name == '__self_class__':
            return Result(self.obj_or_type_type)
        if name == '__self__':
            return Result(self.obj_or_type)
        if name == '__class__':
            return Result(get_guest_builtin('super'))

        start_type = self.obj_or_type_type
        mro = get_mro(start_type)
        # Look at everything succeeding 'type_' in the MRO order.
        i = mro.index(self.type_)
        mro = mro[i+1:]

        for t in mro:
            if _is_type_builtin(t):
                if name == '__new__':
                    return Result(get_guest_builtin('type.__new__'))
                continue
            if _is_object_builtin(t):
                continue
            assert isinstance(t, GuestClass), t
            if name not in t.dict_:
                continue
            cls_attr = t.getattr(name, interp_state=interp_state,
                                 interp_callback=interp_callback)
            if cls_attr.is_exception():
                return cls_attr.get_exception()
            cls_attr = cls_attr.get_value()
            if (not isinstance(self.obj_or_type, GuestClass)
                    and cls_attr.hasattr('__get__')):
                return _invoke_desc(
                    self.obj_or_type, cls_attr, interp_state=interp_state,
                    interp_callback=interp_callback)
            return Result(cls_attr)

        return Result(ExceptionData(
            None, None,
            AttributeError(f"'super' object has no attribute {name!r}")))

    def setattr(self, *args, **kwargs) -> Result[None]:
        return self.obj_or_type.setattr(*args, **kwargs)


def _do_super(args: Tuple[Any, ...],
              interp_state: InterpreterState) -> Result[Any]:
    if not args:
        frame = interp_state.last_frame
        cell = next(cell for cell in frame.cellvars
                    if cell._name == '__class__')
        type_ = cell._storage
        if not isinstance(type_, GuestClass):
            raise NotImplementedError
        obj_or_type = frame.locals_[0]
    else:
        assert len(args) == 2, args
        type_, obj_or_type = args

    if DEBUG_PRINT_BYTECODE:
        print(f'[go:super] type_: {type_} obj: {obj_or_type}', file=sys.stderr)

    def supercheck():
        if isinstance(obj_or_type, GuestClass):
            return obj_or_type
        assert isinstance(obj_or_type, GuestInstance)
        return obj_or_type.get_type()

    obj_type = supercheck()
    return Result(GuestSuper(type_, obj_or_type, obj_type))


_ITER_BUILTIN_TYPES = (
    tuple, str, bytes, bytearray, type({}.keys()), type({}.values()),
    type({}.items()), list, type(reversed([])), type(range(0, 0)),
    set, type(zip((), ())),
)


def _do_iter(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 1

    if isinstance(args[0], _ITER_BUILTIN_TYPES):
        return Result(iter(args[0]))
    raise NotImplementedError(args)


class GuestBuiltin(GuestPyObject):
    """A builtin function in the echo VM."""

    def __init__(self, name: Text, bound_self: Any, singleton_ok: bool = True):
        self.name = name
        self.bound_self = bound_self
        self.dict = {}

    def __repr__(self):
        if self.name == 'object':
            return "<ebuiltin class 'object'>"
        if self.name == 'type':
            return "<eclass 'type'>"
        if self.name == 'super':
            return "<eclass 'super'>"
        return 'GuestBuiltin(name={!r}, bound_self={!r}, ...)'.format(
            self.name, self.bound_self)

    def note_subclass(self, cls: 'GuestClass') -> None:
        pass

    def is_subtype_of(self, other: 'GuestClass') -> bool:
        return False

    @check_result
    def invoke(self, args: Tuple[Any, ...], *,
               interp_state: InterpreterState,
               kwargs: Optional[Dict[Text, Any]] = None,
               # Needed for interface compatibility.
               interp_callback: Callable,
               call: Callable) -> Result[Any]:
        if self.name == 'dict.keys':
            assert not args, args
            return Result(self.bound_self.keys())
        if self.name == 'dict.values':
            assert not args, args
            return Result(self.bound_self.values())
        if self.name == 'dict.items':
            assert not args, args
            return Result(self.bound_self.items())
        if self.name == 'dict.update':
            return Result(self.bound_self.update(args[0]))
        if self.name == 'str.format':
            return Result(self.bound_self.format(*args))
        if self.name == 'str.join':
            return Result(self.bound_self.join(*args))
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
        if self.name == 'zip':
            return Result(zip(*args))
        if self.name == 'reversed':
            return Result(reversed(*args))
        if self.name == 'chr':
            return Result(chr(*args))
        if self.name == 'isinstance':
            return _do_isinstance(args, call=call, interp_state=interp_state,
                                  interp_callback=interp_callback)
        if self.name == 'issubclass':
            return _do_issubclass(args, call=call, interp_state=interp_state,
                                  interp_callback=interp_callback)
        if self.name == '__build_class__':
            return _do___build_class__(
                args, kwargs=kwargs, call=call, interp_state=interp_state,
                interp_callback=interp_callback)
        if self.name == 'type.__new__':
            return _do_type_new(
                args, kwargs=kwargs, call=call, interp_state=interp_state,
                interp_callback=interp_callback)
        if self.name == 'type.__subclasses__':
            return _do_type_subclasses(
                args, kwargs=kwargs, call=call, interp_state=interp_state,
                interp_callback=interp_callback)
        if self.name == 'object.__subclasshook__':
            return _do_object_subclasshook(
                args, kwargs=kwargs, call=call, interp_state=interp_state,
                interp_callback=interp_callback)
        if self.name == 'super':
            return _do_super(args, interp_state)
        if self.name == 'iter':
            return _do_iter(args)
        if self.name == 'type':
            return _do_type(args)
        if self.name == 'next':
            return _do_next(args)
        if self.name == 'hasattr':
            return _do_hasattr(args)
        if self.name == 'repr':
            return _do_repr(args, call)
        if self.name == 'str':
            return _do_str(args, call)
        if self.name == 'object':
            return _do_object(args)
        if self.name == 'dir':
            return _do_dir(args, call, interp_state=interp_state,
                           interp_callback=interp_callback)
        raise NotImplementedError(self.name)

    def hasattr(self, name: Text) -> bool:
        if (self.name in ('object', 'type')
                and name in ('__subclasshook__', '__str__')):
            return True
        return name in self.dict

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if self.name == 'object':
            if name == '__init__':
                return Result(get_guest_builtin('object.__init__'))
            if name == '__str__':
                return Result(get_guest_builtin('object.__str__'))
            if name == '__bases__':
                return Result(())
        if self.name == 'type':
            if name == '__new__':
                return Result(get_guest_builtin('type.__new__'))
            if name == '__subclasshook__':
                return Result(get_guest_builtin('object.__subclasshook__'))
            if name == '__subclasses__':
                return Result(get_guest_builtin('type.__subclasses__'))
        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


@memoize
def get_guest_builtin(name: Text) -> GuestBuiltin:
    return GuestBuiltin(name, None)


class GuestPartial:
    def __init__(self, f: GuestFunction, args: Tuple[Any, ...]):
        assert isinstance(f, GuestFunction), f
        self.f = f
        self.args = args

    @check_result
    def invoke(self, args: Tuple[Any, ...], *,
               interp_state: InterpreterState,
               interp_callback: Callable) -> Any:
        return self.f.invoke(
            args=self.args + args, kwargs=None,
            interp_callback=interp_callback, interp_state=interp_state)


class NativeFunction(GuestPyObject):

    def __init__(self, f: Callable, name: Text):
        self.f = f
        self.name = name

    def get_type(self) -> GuestPyObject:
        return GuestFunctionType.singleton

    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError

    @check_result
    def invoke(self, *, args: Tuple[Any, ...],
               interp_callback: Callable,
               interp_state: InterpreterState,
               kwargs: Optional[Dict[Text, Any]] = None,
               locals_dict: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        return self.f(args, interp_state=interp_state,
                      interp_callback=interp_callback)


class GuestProperty(GuestPyObject):
    def __init__(self, fget: GuestFunction):
        self.fget = fget

    def hasattr(self, name: Text):
        return name in ('__get__', '__set__')

    @check_result
    def _get(self, args: Tuple[Any, ...], *,
             interp_state: InterpreterState,
             interp_callback: Callable) -> Result[Any]:
        #print('GuestProperty.__get__ args:', args)
        _self, obj, objtype = args
        assert _self is self
        return self.fget.invoke(args=(obj,), interp_callback=interp_callback,
                                interp_state=interp_state)

    @check_result
    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None
                ) -> Result[Any]:
        if name == '__get__':
            return Result(GuestMethod(NativeFunction(
                self._get, 'eproperty.__get__'), bound_self=self))
        return Result(ExceptionData(None, name, AttributeError))

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError


class GuestClassMethod(GuestPyObject):
    def __init__(self, f: GuestFunction):
        self.f = f
        self.dict_ = {}

    def __repr__(self) -> Text:
        return '<eclassmethod object at {:#x}>'.format(id(self))

    def invoke(self, *args, **kwargs) -> Result[Any]:
        return self.f.invoke(*args, **kwargs)

    def hasattr(self, name: Text) -> bool:
        return name in self.dict_ or name == '__get__'

    @check_result
    def _get(self, args: Tuple[Any, ...], *,
             interp_state: InterpreterState,
             interp_callback: Callable) -> Result[Any]:
        _self, obj, objtype = args
        assert _self is self
        if obj is not None:
            objtype = _do_type(args=(obj,))
        return Result(GuestMethod(self.f, bound_self=objtype))

    @check_result
    def getattr(self, name: Text,
                *,
                interp_state: InterpreterState,
                interp_callback: Optional[Callable] = None,
                ) -> Result[Any]:
        if name == '__get__':
            #print('eclassmethod.__get__', file=sys.stderr)
            return Result(GuestMethod(NativeFunction(
                self._get, 'eclassmethod.__get__'), bound_self=self))
        if name == '__func__':
            return Result(self.f)
        raise NotImplementedError(name)

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError(name, value)


class GuestCell:
    def __init__(self, name: Text):
        self._name = name
        self._storage = GuestCell

    def __repr__(self):
        return 'GuestCell(_name={!r}, _storage={})'.format(
            self._name,
            '<empty>' if self._storage is GuestCell else repr(self._storage))

    def initialized(self) -> bool:
        return self._storage is not GuestCell

    def get(self) -> Any:
        assert self._storage is not GuestCell, (
            'GuestCell %r is uninitialized' % self._name)
        return self._storage

    def set(self, value: Any):
        self._storage = value
