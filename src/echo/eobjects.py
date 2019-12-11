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
import weakref

from echo.return_kind import ReturnKind
from echo.epy_object import EPyObject, AttrWhere, EPyType
from echo.elog import log, debugged
from echo.interpreter_state import InterpreterState
from echo.interp_context import ICtx
from echo.code_attributes import CodeAttributes
from echo.interp_result import Result, ExceptionData, check_result
from echo.value import Value
from echo.common import memoize


class EFunction(EPyObject):
    def __init__(self,
                 code: types.CodeType,
                 globals_: Dict[Text, Any],
                 name: Text,
                 *,
                 defaults=None,
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
            '__module__': None,
            '__doc__': None,
            '__qualname__': None,
            '__name__': name,
        }

    def get_type(self) -> EPyObject:
        return EFunctionType.singleton

    def __repr__(self):
        return '<efunction {} at {:#x}>'.format(self.name, id(self))

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
        if self._code_attrs.coroutine:
            return Result(GuestCoroutine(self))

        return ictx.interp_callback(
            self.code, globals_=self.globals_, args=args, kwargs=kwargs,
            defaults=self.defaults, locals_dict=locals_dict, name=self.name,
            kwarg_defaults=self.kwarg_defaults, closure=self.closure,
            ictx=ictx)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict_:
            return AttrWhere.SELF_DICT
        if name in ('__class__',):
            return AttrWhere.SELF_SPECIAL
        if name in ('__get__',):
            return AttrWhere.CLS
        return None

    def _get(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
        assert len(args) == 3, args
        _self, obj, objtype = args
        assert self is _self
        if obj is None:
            return Result(_self)
        return Result(EMethod(f=_self, bound_self=obj))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__class__':
            return Result(EFunctionType.singleton)
        if name == '__get__':
            return Result(EMethod(NativeFunction(
                self._get, 'efunction.__get__'), bound_self=self))
        try:
            return Result(self.dict_[name])
        except KeyError:
            return Result(ExceptionData(None, name, AttributeError))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        self.dict_[name] = value
        return Result(None)


class GuestCoroutine(EPyObject):
    def __init__(self, f: EFunction):
        self.f = f

    def get_type(self) -> EPyObject:
        return GuestCoroutineType.singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name == 'close':
            return AttrWhere.CLS
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == 'close':
            def fake(x): pass
            guest_f = EFunction(
                getattr(fake, '__code__'), {}, 'coroutine.close')
            guest_m = EMethod(guest_f, self)
            return Result(guest_m)
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class EAsyncGeneratorType(EPyObject):
    def __init__(self):
        self._dict = {}

    def __repr__(self) -> Text:
        return "<eclass 'async_generator'>"

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__mro__':
            return Result((self, get_guest_builtin('type')))
        if name == '__dict__':
            return Result(self._dict)
        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        return None


EAsyncGeneratorType.singleton = EAsyncGeneratorType()


class EAsyncGenerator(EPyObject):
    def __init__(self, f):
        self.f = f

    def get_type(self) -> EPyObject:
        return EAsyncGeneratorType.singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


class EMethodType(EPyObject):
    def __repr__(self) -> Text:
        return "<eclass 'method'>"

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None


EMethodType.singleton = EMethodType()


class EMethod(EPyObject):

    def __init__(self, f: Union[EFunction, 'NativeFunction'], bound_self):
        self.f = f
        self.bound_self = bound_self

    def __repr__(self) -> Text:
        return '<ebound method {} of {!r}>'.format(
            self.f.name, self.bound_self)

    def get_type(self) -> EPyObject:
        return EMethodType.singleton

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

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__self__', '__func__'):
            return AttrWhere.SELF_SPECIAL
        if name == '__get__':
            return None
        return None

    def getattr(self, name: Text, *args, **kwargs) -> Result[Any]:
        if name == '__self__':
            return Result(self.bound_self)
        if name == '__func__':
            return Result(self.f)
        return self.f.getattr(name, *args, **kwargs)

    def setattr(self, *args, **kwargs):
        return self.f.setattr(*args, **kwargs)

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
        return self.f.invoke(
            (self.bound_self,) + args,
            kwargs, locals_dict, ictx)


@check_result
def _invoke_desc(self, cls_attr, ictx: ICtx) -> Result[Any]:
    assert cls_attr.hasattr('__get__')

    # Grab the descriptor getter off the descriptor.
    f_result = cls_attr.getattr('__get__', ictx)
    if f_result.is_exception():
        return Result(f_result.get_exception())
    f = f_result.get_value()

    # Determine the type of obj.
    objtype_result = do_type((cls_attr,), {})
    if objtype_result.is_exception():
        return Result(objtype_result.get_exception())
    objtype = objtype_result.get_value()

    ictx.desc_count += 1

    return f.invoke((self, objtype), {}, {}, ictx)


class EInstance(EPyObject):

    builtin_storage: Dict[type, Any]

    def __init__(self, cls: Union['EClass', 'EBuiltin']):
        assert isinstance(cls, (EClass, EBuiltin)), cls
        self.cls = cls
        self.dict_ = {}
        self.builtin_storage = {}

    def __repr__(self) -> Text:
        return '<{} eobject>'.format(self.cls.name)

    def get_type(self) -> Union['EClass', 'EBuiltin']:
        return self.cls

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict_:
            return AttrWhere.SELF_DICT
        # Special members.
        if name in ('__class__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        cls_hasattr = self.cls.hasattr(name)
        assert isinstance(cls_hasattr, bool), (self.cls, cls_hasattr)
        return AttrWhere.CLS if cls_hasattr else None

    def _search_mro_for(self, name: Text, ictx: ICtx) -> Optional[Any]:
        for cls in self.cls.get_mro():
            if isinstance(cls, EBuiltin):
                if cls.hasattr(name):
                    return cls.getattr(name, ictx).get_value()
                continue
            assert isinstance(cls, EClass), cls
            if name in cls.dict_:
                return cls.dict_[name]
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        cls_attr = self._search_mro_for(name, ictx)

        log('gi:ga', f'self: {self} name: {name} cls_attr: {cls_attr}')

        if (isinstance(cls_attr, EInstance)
                and cls_attr.hasattr('__get__')
                and cls_attr.hasattr('__set__')):
            log('gi:ga', f'overriding descriptor: {cls_attr}')
            # Overriding descriptor.
            return _invoke_desc(self, cls_attr, ictx)

        try:
            return Result(self.dict_[name])
        except KeyError:
            if name == '__class__':
                return Result(self.cls)
            if name == '__dict__':
                return Result(self.dict_)

        log('eo:ei', f'cls_attr: {cls_attr}')
        if isinstance(cls_attr, EPyObject) and cls_attr.hasattr('__get__'):
            log('gi:ga', f'non-overriding descriptor: {cls_attr}')
            return _invoke_desc(self, cls_attr, ictx)

        if cls_attr is not None:
            return Result(cls_attr)

        return Result(ExceptionData(
            None,
            f"'{self.cls.name}' object does not have attribute {name!r}",
            AttributeError))

    @check_result
    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        cls_attr = None
        if name in self.cls.dict_:
            cls_attr = self.cls.dict_[name]

        if (isinstance(cls_attr, EInstance)
                and cls_attr.hasattr('__set__')):
            f_result = cls_attr.getattr('__set__', ictx)
            if f_result.is_exception():
                return Result(f_result.get_exception())
            return f_result.get_value().invoke((self, value), {}, {}, ictx)

        self.dict_[name] = value
        return Result(None)


def register_builtin(
        name: Text,
        type_: Optional[type] = None) -> Callable[[Callable], Callable]:
    def fregister(f: Callable) -> Callable:
        EBuiltin.register(name, f, type_)
        return f
    return fregister


EClassOrBuiltin = Union['EClass', 'EBuiltin']


def _get_bases(c: EClassOrBuiltin) -> Tuple[EPyObject, ...]:
    assert isinstance(c, (EClass, EBuiltin)), c
    if isinstance(c, EClass):
        return c.bases
    if _is_type_builtin(c) or _is_dict_builtin(c):
        return (get_guest_builtin('object'),)
    if _is_object_builtin(c):
        return ()
    raise NotImplementedError(c)


class EClass(EPyType):
    """Represents a user-defined class."""

    bases: Tuple[EClassOrBuiltin, ...]
    metaclass: Optional[EClassOrBuiltin]
    subclasses: Set['EClass']

    def __init__(self, name: Text, dict_: Dict[Text, Any], *,
                 bases: Optional[Tuple[EClassOrBuiltin]] = None,
                 metaclass=None, kwargs=None):
        self.name = name
        self.dict_ = dict_
        self.bases = bases or ()
        self.metaclass = metaclass
        self.kwargs = kwargs
        self.subclasses = weakref.WeakSet()

        for base in self.bases:
            if isinstance(base, (EBuiltin, EClass)):
                base.note_subclass(self)

    def note_subclass(self, derived: 'EClass') -> None:
        self.subclasses.add(derived)

    def __repr__(self) -> Text:
        if '__module__' in self.dict_:
            return '<eclass \'{}.{}\'>'.format(
                self.dict_['__module__'], self.name)
        return '<eclass \'{}\">'.format(self.name)

    def get_type(self) -> 'EClass':
        return self.metaclass or get_guest_builtin('type')

    def get_mro(self) -> Tuple['EPyObject', ...]:
        """The MRO is a preorder DFS of the 'derives from' relation."""
        derives_from = []  # (cls, base)
        frontier = collections.deque([self])
        while frontier:
            cls = frontier.popleft()
            for base in _get_bases(cls):
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
            for b in reversed(_get_bases(c)):
                if is_ready(b):
                    ready.appendleft(b)

        eobject = get_guest_builtin('object')

        if eobject not in order:
            order.append(eobject)
        return tuple(order)

    def instantiate(self,
                    args: Tuple[Any, ...],
                    kwargs: Dict[Text, Any],
                    globals_: Dict[Text, Any],
                    ictx: ICtx) -> Result[EInstance]:
        """Creates an instance of this user-defined class."""
        log('go:gc', f'instantiate self: {self} args: {args} kwargs: {kwargs}')
        guest_instance = None
        if self.hasattr('__new__'):
            new_f = self.getattr('__new__', ictx).get_value()
            log('gc:new', f'new_f {new_f}')
            result = ictx.call(new_f, (self,) + args, kwargs, locals_dict={},
                               globals_=globals_)
            if result.is_exception():
                return Result(result.get_exception())
            guest_instance = result.get_value()
            if not _do_isinstance((guest_instance, self), ictx).get_value():
                return Result(guest_instance)
        guest_instance = guest_instance or EInstance(self)
        if self.hasattr('__init__'):
            init_f = self.getattr('__init__', ictx).get_value()
            # TODO(cdleary, 2019-01-26) What does Python do when you return
            # something non-None from initializer? Ignore?
            assert isinstance(guest_instance, EPyObject), guest_instance
            result = ictx.call(init_f,
                               (guest_instance,) + args,
                               kwargs,
                               {},
                               globals_=globals_)
            if result.is_exception():
                return result
        return Result(guest_instance)

    @debugged('go:eclass:hasattr_where()')
    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict_:
            return AttrWhere.SELF_DICT
        if name in ('__class__', '__bases__', '__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        for base in self.get_mro()[1:]:
            haw = base.hasattr_where(name)
            if haw:
                return haw
        if self.get_type().hasattr(name):
            return AttrWhere.CLS
        return None

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__dict__':
            return Result(self.dict_)

        if name in self.dict_:
            v = self.dict_[name]
            if isinstance(v, EPyObject) and v.hasattr('__get__'):
                f_result = v.getattr('__get__', ictx)
                if f_result.is_exception():
                    return Result(f_result.get_exception())
                return f_result.get_value().invoke((None, self), {}, {}, ictx)
            return Result(v)

        if name == '__mro__':
            return Result(self.get_mro())
        if name == '__class__':
            return Result(self.metaclass or get_guest_builtin('type'))
        if name == '__bases__':
            return Result(self.bases)
        if name == '__subclasses__':
            return Result(get_guest_builtin('type.__subclasses__'))
        log('ga', f'bases: {self.bases} metaclass: {self.metaclass}')

        for base in self.get_mro()[1:]:
            ha = do_hasattr((base, name)).get_value()
            log('ga', f'checking base: {base} for {name} => {ha}')
            if ha:
                return do_getattr((base, name), {}, ictx)

        if self.metaclass and self.metaclass.hasattr(name):
            return self.metaclass.getattr(name, ictx)

        return Result(ExceptionData(
            None,
            f'Class {self.name} does not have attribute {name!r}',
            AttributeError))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        self.dict_[name] = value
        return Result(None)


class EFunctionType(EPyObject):
    def __repr__(self) -> Text:
        return "<eclass 'function'>"

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__code__', '__globals__', '__get__'):
            return AttrWhere.SELF_SPECIAL
        return None

    def _get_desc(self, args, kwargs: Dict[Text, Any],
                  locals_dict: Dict[Text, Any],
                  ictx: ICtx) -> Result[Any]:
        assert not kwargs, kwargs
        assert len(args) == 3, args
        self, obj, objtype = args
        if obj is None:
            return Result(self)
        return Result(EMethod(self, bound_self=obj))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name in ('__code__', '__globals__'):
            return Result(None)

        if name == '__get__':
            return Result(NativeFunction(self._get_desc, 'efunction.__get__'))

        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError


EFunctionType.singleton = EFunctionType()


class GuestCoroutineType(EPyObject):

    def __init__(self):
        self.dict_ = {}

    def get_type(self) -> EPyObject:
        return get_guest_builtin('type')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__mro__':
            return Result((self, get_guest_builtin('type')))
        if name == '__dict__':
            return Result(self.dict_)
        raise NotImplementedError(name)

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(name, value)


GuestCoroutineType.singleton = GuestCoroutineType()


def _is_type_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'type'


def _is_dict_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'dict'


def _is_list_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'list'


def _is_object_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'object'


def _is_str_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'str'


def _is_tuple_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'tuple'


@check_result
def _do_isinstance(
        args: Tuple[Any, ...],
        ictx: ICtx) -> Result[bool]:
    assert len(args) == 2, args

    if (isinstance(args[1], EClass) and
            args[1].hasattr('__instancecheck__')):
        ic = args[1].getattr('__instancecheck__', ictx)
        if ic.is_exception():
            return Result(ic.get_exception())
        ic = ic.get_value()
        result = ictx.call(ic, (args[1], args[0]), {}, {},
                           globals_=ic.globals_)
        return result

    for t in (bool, int, str, float, dict, list, tuple, set):
        if args[1] is t:
            return Result(isinstance(args[0], t))

    if args[1] is type:
        return Result(isinstance(args[0], (type, EClass)))

    if isinstance(args[1], type) and issubclass(args[1], Exception):
        # TODO(leary) How does the real type builtin make it here?
        return Result(isinstance(args[0], args[1]))

    if _is_tuple_builtin(args[1]):
        if not isinstance(args[0], EPyObject):
            return Result(isinstance(args[0], tuple))
        raise NotImplementedError(args)

    if _is_type_builtin(args[1]):
        if _is_type_builtin(args[0]) or _is_object_builtin(args[0]):
            return Result(True)
        lhs_type = do_type((args[0],), {})
        if lhs_type.is_exception():
            return Result(lhs_type.get_exception())
        result = _do_issubclass(
            (lhs_type.get_value(), get_guest_builtin('type')), ictx)
        log('go:isinstance', f'args: {args} result: {result}')
        return result

    if _is_str_builtin(args[1]):
        return Result(isinstance(args[0], str))

    if _is_dict_builtin(args[1]):
        return Result(isinstance(args[0], dict))

    if _is_list_builtin(args[1]):
        return Result(isinstance(args[0], list))

    if _is_object_builtin(args[1]):
        return Result(True)  # Everything is an object.

    if args[0] is None:
        return Result(args[1] is type(None))  # noqa

    if (not isinstance(args[0], EPyObject)
            and isinstance(args[1], EClass)):
        return Result(type(args[0]) in args[1].get_mro())

    if isinstance(args[0], EPyObject):
        if isinstance(args[1], EClass):
            return Result(args[0].get_type() in args[1].get_mro())
        if args[0].get_type() == args[1]:
            return Result(True)

    raise NotImplementedError(args)


@check_result
def _do_issubclass(
        args: Tuple[Any, ...],
        ictx: ICtx) -> Result[bool]:
    assert len(args) == 2, args
    log('go:issubclass', f'arg0: {args[0]}')
    log('go:issubclass', f'arg1: {args[1]}')

    if args[0] is args[1] and isinstance(args[0], EBuiltin):
        return Result(True)

    if (isinstance(args[1], EPyObject) and
            args[1].hasattr('__subclasscheck__')):
        scc = args[1].getattr('__subclasscheck__', ictx)
        if scc.is_exception():
            return Result(scc.get_exception())
        scc = scc.get_value()
        result = ictx.call(scc, (args[1], args[0]), {}, {},
                           globals_=scc.globals_)
        return result

    if isinstance(args[0], EClass) and isinstance(args[1], EBuiltin):
        return Result(args[0].is_subtype_of(args[1]))

    if isinstance(args[0], EPyType) and isinstance(args[1], EPyType):
        return Result(args[0].is_subtype_of(args[1]))

    if ((isinstance(args[0], EPyObject)
         and not isinstance(args[1], EPyObject)) or
        (not isinstance(args[0], EPyObject)
         and isinstance(args[1], EPyObject))):
        return Result(False)

    if isinstance(args[0], EBuiltin) and isinstance(args[1], EPyType):
        return Result(False)

    if isinstance(args[0], GuestCoroutineType):
        return Result(_is_type_builtin(args[1]))

    if _is_object_builtin(args[0]) and _is_type_builtin(args[1]):
        return Result(False)

    if _is_object_builtin(args[1]):
        return Result(True)

    if isinstance(args[1], GuestCoroutineType):
        return Result(False)

    if _is_type_builtin(args[1]):
        if isinstance(args[0], EPyObject):
            result = args[0].get_type().is_subtype_of(
                get_guest_builtin('type'))
            assert isinstance(result, bool), result
            return Result(result)
        if isinstance(args[0], type):
            return Result(issubclass(args[0], type))

    if isinstance(args[0], EClass):
        return Result(args[1] in args[0].get_mro())

    if isinstance(args[0], type) and isinstance(args[1], type):
        return Result(issubclass(args[0], args[1]))

    raise NotImplementedError(args)


@check_result
def _do_next(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 1, args
    g = args[0]
    return g.next()


@check_result
def _do_repr(args: Tuple[Any, ...], ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if not isinstance(o, EPyObject):
        return Result(repr(o))
    frepr = o.getattr('__repr__', ictx)
    if frepr.is_exception():
        return frepr
    frepr = frepr.get_value()
    log('go:do_repr()', f'o: {o} frepr: {frepr}')
    globals_ = frepr.globals_
    return ictx.call(frepr, args=(), kwargs={}, locals_dict={},
                     globals_=globals_)


@check_result
def _do_str(args: Tuple[Any, ...], ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if not isinstance(o, EPyObject):
        return Result(repr(o))
    frepr = o.getattr('__str__')
    if frepr.is_exception():
        return frepr
    frepr = frepr.get_value()
    globals_ = frepr.getattr('__globals__')
    return ictx.call(frepr, args=(), globals_=globals_)


@check_result
def _do_object(args: Tuple[Any, ...]) -> Result[Any]:
    assert len(args) == 0, args
    return Result(EInstance(cls=get_guest_builtin('object')))


@check_result
def _do_type_new(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[EClass]:
    if kwargs:
        kwarg_metaclass = kwargs.pop('metaclass', args[0])
        assert kwarg_metaclass is args[0]
        assert not kwargs, kwargs
    if len(args) != 4:
        msg = f"Expected 4 arguments to type.__new__, got {len(args)}"
        return Result(ExceptionData(
            None, None,
            TypeError(msg)))
    metaclass, name, bases, ns = args
    cls = EClass(name, dict_=ns, bases=bases, metaclass=metaclass)
    return Result(cls)


@check_result
def _do_type_subclasses(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    c = args[0]
    assert isinstance(c, EClass), c
    return Result(sorted(list(c.subclasses)))


@check_result
def _do_object_subclasshook(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    return Result(NotImplemented)


@check_result
def _do_object_eq(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert not kwargs
    assert len(args) == 2, args
    lhs, rhs = args
    return Result(NotImplemented)


@check_result
def _do_object_new(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) >= 1, args
    assert isinstance(args[0], (EClass, EBuiltin)), args
    return Result(EInstance(args[0]))


@check_result
def _do_object_init(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) >= 1, args
    assert isinstance(args[0], (EInstance)), args
    return Result(None)


@check_result
def _do_object_repr(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1 and not kwargs, (args, kwargs)
    raise NotImplementedError(args[0])


@check_result
def _do_object_ne(
        args: Tuple[Any, ...],
        kwargs: Dict[Text, Any],
        ictx: ICtx) -> Result[Any]:
    assert not kwargs
    lhs, rhs = args
    return Result(NotImplemented)


@check_result
def _do_dir(args: Tuple[Any, ...],
            kwargs: Dict[Text, Any],
            ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if isinstance(o, EPyObject):
        d = o.getattr('__dict__', ictx)
        if d.is_exception():
            return d.get_exception()
        d = d.get_value()
        keys = set(d.keys())
        keys.add('__class__')
        keys.add('__dict__')
        if isinstance(o, EInstance):
            result = _do_dir((o.cls,), kwargs, ictx)
            if result.is_exception():
                return Result(result.get_exception())
            assert isinstance(result.get_value(), list), result
            keys |= set(result.get_value())
        return Result(sorted(list(keys)))
    return Result(dir(o))


def _get_mro(o: EPyObject) -> Tuple[EPyObject, ...]:
    if isinstance(o, EBuiltin):
        return o.get_mro()
    assert isinstance(o, EClass), o
    return o.get_mro()


class ESuper(EPyObject):
    def __init__(self, type_, obj_or_type, obj_or_type_type):
        self.type_ = type_
        self.obj_or_type = obj_or_type
        self.obj_or_type_type = obj_or_type_type

    def get_type(self) -> 'EPyObject':
        return get_guest_builtin('super')

    def __repr__(self) -> Text:
        return "<esuper: <class '{}'>, <{} object>>".format(
            self.type_.name, self.obj_or_type_type.name)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__thisclass__', '__self_class__', '__self__',
                    '__class__'):
            return AttrWhere.SELF_SPECIAL

        start_type = self.obj_or_type_type
        mro = _get_mro(start_type)
        # Look at everything succeeding 'type_' in the MRO order.
        i = mro.index(self.type_)
        mro = mro[i+1:]

        for t in mro:
            if _is_type_builtin(t):
                if name == '__new__':
                    return AttrWhere.SELF_SPECIAL
                continue
            if _is_object_builtin(t):
                continue
            assert isinstance(t, EClass), t
            if name in t.dict_:
                return AttrWhere.SELF_SPECIAL

        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__thisclass__':
            return Result(self.type_)
        if name == '__self_class__':
            return Result(self.obj_or_type_type)
        if name == '__self__':
            return Result(self.obj_or_type)
        if name == '__class__':
            return Result(get_guest_builtin('super'))

        start_type = self.obj_or_type_type
        mro = _get_mro(start_type)
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
            assert isinstance(t, EClass), t
            if name not in t.dict_:
                continue
            # Name is in this class within the MRO, grab the attr.
            cls_attr = t.getattr(name, ictx)
            if cls_attr.is_exception():
                return cls_attr.get_exception()
            cls_attr = cls_attr.get_value()
            if (not isinstance(self.obj_or_type, EClass)
                    and cls_attr.hasattr('__get__')):
                return _invoke_desc(self.obj_or_type, cls_attr, ictx)
            return Result(cls_attr)

        return Result(ExceptionData(
            None, None,
            AttributeError(f"'super' object has no attribute {name!r}")))

    def setattr(self, *args, **kwargs) -> Result[None]:
        return self.obj_or_type.setattr(*args, **kwargs)


@check_result
def _do_super(args: Tuple[Any, ...],
              ictx: ICtx) -> Result[Any]:
    if not args:
        frame = ictx.interp_state.last_frame
        if frame is None:
            return Result(ExceptionData(
                traceback=None, parameter=None,
                exception=RuntimeError('super(): no current frame')))
        cell = next(cell for cell in frame.cellvars
                    if cell._name == '__class__')
        type_ = cell._storage
        if not isinstance(type_, EClass):
            raise NotImplementedError
        obj_or_type = frame.locals_[0]
    else:
        assert len(args) == 2, args
        type_, obj_or_type = args

    log('super', f'type_: {type_} obj: {obj_or_type}')

    def supercheck():
        if isinstance(obj_or_type, EClass):
            return obj_or_type
        assert isinstance(obj_or_type, EInstance)
        return obj_or_type.get_type()

    obj_type = supercheck()
    return Result(ESuper(type_, obj_or_type, obj_type))


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


class EBuiltin(EPyType):
    """A builtin function/type in the echo VM."""

    BUILTIN_TYPES = ('object', 'type', 'dict', 'tuple', 'list')

    _registry: Dict[Text, Tuple[Callable, Optional[type]]] = {}

    def __init__(self, name: Text, bound_self: Any, singleton_ok: bool = True):
        self.name = name
        self.bound_self = bound_self
        self.dict = {}
        self.globals_ = {}

    @classmethod
    def is_ebuiltin(cls, o: Any) -> bool:
        if isinstance(o, EBuiltin):
            return True
        return o in cls._registry.values()

    @classmethod
    def get_ebuiltin_type(cls, name: Text) -> type:
        t = cls._registry[name][1]
        assert t is not None
        return t

    @classmethod
    def register(cls, name: Text, f: Callable, t: Optional[type]) -> None:
        cls._registry[name] = (f, t)

    def __repr__(self):
        if self.name == 'object':
            return "<eclass 'object'>"
        if self.name == 'type':
            return "<eclass 'type'>"
        if self.name == 'super':
            return "<eclass 'super'>"
        return 'EBuiltin(name={!r}, bound_self={!r}, ...)'.format(
            self.name, self.bound_self)

    def get_type(self) -> EPyObject:
        if self.name in ('object.__init__', 'object.__str__', 'dict.__eq__',
                         'dict.fromkeys', 'dict.update'):
            if self.bound_self:
                return EMethodType.singleton
            else:
                return EFunctionType.singleton
        if self.name in self.BUILTIN_TYPES:
            return get_guest_builtin('type')
        raise NotImplementedError(self)

    def get_mro(self) -> Tuple['EPyObject', ...]:
        if self.name == 'object':
            return (get_guest_builtin('object'),)
        elif self.name in self.BUILTIN_TYPES:
            return (get_guest_builtin(self.name), get_guest_builtin('object'))
        else:
            raise NotImplementedError(self)

    def note_subclass(self, cls: 'EClass') -> None:
        pass

    def is_subtype_of(self, other: EPyType) -> bool:
        if _is_type_builtin(self) and _is_object_builtin(other):
            return True
        return False

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
        if self.name == 'dict.keys':
            assert not args, args
            return Result(self.bound_self.keys())
        if self.name == 'dict.values':
            assert not args, args
            return Result(self.bound_self.values())
        if self.name == 'dict.items':
            assert not args, args
            return Result(self.bound_self.items())
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
            return _do_isinstance(args, ictx)
        if self.name == 'issubclass':
            return _do_issubclass(args, ictx)
        if self.name == 'type.__new__':
            return _do_type_new(args, kwargs, ictx)
        if self.name == 'type.__subclasses__':
            return _do_type_subclasses(args, kwargs, ictx)
        if self.name == 'object.__subclasshook__':
            return _do_object_subclasshook(args, kwargs, ictx)
        if self.name == 'object.__new__':
            return _do_object_new(args, kwargs, ictx)
        if self.name == 'object.__init__':
            return _do_object_init(args, kwargs, ictx)
        if self.name == 'object.__repr__':
            if self.bound_self is not None:
                args = (self.bound_self,) + args
            return _do_object_repr(args, kwargs, ictx)
        if self.name == 'object.__eq__':
            return _do_object_eq(args, kwargs, ictx)
        if self.name == 'object.__ne__':
            return _do_object_ne(args, kwargs, ictx)
        if self.name == 'super':
            return _do_super(args, ictx)
        if self.name == 'iter':
            return _do_iter(args)
        if self.name == 'type':
            return do_type(args, {})
        if self.name == 'next':
            return _do_next(args)
        if self.name == 'hasattr':
            return do_hasattr(args)
        if self.name == 'repr':
            return _do_repr(args, ictx)
        if self.name == 'str':
            return _do_str(args, ictx)
        if self.name == 'object':
            return _do_object(args)
        if self.name == 'dir':
            return _do_dir(args, kwargs, ictx)
        if self.name == 'getattr':
            return do_getattr(args, kwargs, ictx)
        if self.name in self._registry:
            if self.bound_self is not None:
                args = (self.bound_self,) + args
            return self._registry[self.name][0](args, kwargs, ictx)
        raise NotImplementedError(self.name)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict:
            return AttrWhere.SELF_DICT
        if self.name == 'dict' and name in (
                'update', 'setdefault', '__eq__', '__getitem__', '__setitem__',
                '__delitem__'):
            return AttrWhere.SELF_SPECIAL
        if (self.name in self.BUILTIN_TYPES
                and name in ('__mro__', '__dict__',)):
            return AttrWhere.SELF_SPECIAL
        if (self.name in ('dict.update', 'dict.setdefault', 'dict.__eq__',
                          'dict.__getitem__', 'dict.__setitem__',
                          'dict.__delitem__')
                and name == '__get__'):
            return AttrWhere.CLS
        if (self.name in ('object', 'type', 'dict', 'tuple')
                and name in ('__new__', '__init__', '__dict__', '__str__',
                             '__repr__', '__eq__', '__ne__', '__new__',
                             '__name__')):
            return AttrWhere.SELF_SPECIAL
        if self.name == 'object' and name in ('__subclasshook__', '__bases__'):
            return AttrWhere.SELF_SPECIAL
        if self.name == 'type' and name in ('__subclasses__',):
            return AttrWhere.SELF_SPECIAL
        if name == '__eq__':
            return AttrWhere.CLS
        return None

    @debugged('eo:ebi')
    def _get(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
        assert len(args) == 3, args
        _self, obj, objtype = args
        assert self is _self
        if obj is None:
            return Result(_self)
        return Result(EMethod(f=_self, bound_self=obj))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__self__' and self.bound_self is not None:
            return Result(self.bound_self)

        if self.name == 'dict':
            if name == '__new__':
                return Result(get_guest_builtin('dict.__new__'))
            if name == '__init__':
                return Result(get_guest_builtin('dict.__init__'))
            if name == '__eq__':
                return Result(get_guest_builtin('dict.__eq__'))
            if name == '__getitem__':
                return Result(get_guest_builtin('dict.__getitem__'))
            if name == '__setitem__':
                return Result(get_guest_builtin('dict.__setitem__'))
            if name == '__delitem__':
                return Result(get_guest_builtin('dict.__delitem__'))
            if name == 'update':
                return Result(get_guest_builtin('dict.update'))
            if name == '__dict__':
                return Result({
                    'fromkeys': get_guest_builtin('dict.fromkeys'),
                })
            if name == 'setdefault':
                return Result(get_guest_builtin('dict.setdefault'))

        if self.name in ('dict.update', 'dict.__eq__') and name == '__get__':
            return Result(EMethod(NativeFunction(
                self._get, 'ebuiltin.__get__'), bound_self=self))

        if self.name == 'object':
            if name == '__new__':
                return Result(get_guest_builtin('object.__new__'))
            if name == '__init__':
                return Result(get_guest_builtin('object.__init__'))
            if name == '__str__':
                return Result(get_guest_builtin('object.__str__'))
            if name == '__repr__':
                return Result(get_guest_builtin('object.__repr__'))
            if name == '__subclasshook__':
                return Result(get_guest_builtin('object.__subclasshook__'))
            if name == '__bases__':
                return Result(())
            if name == '__dict__':  # Fake it for now.
                return Result({})
        if self.name == 'type':
            if name == '__new__':
                return Result(get_guest_builtin('type.__new__'))
            if name == '__name__':
                return Result(get_guest_builtin('type.__name__'))
            if name == '__repr__':
                return Result(get_guest_builtin('type.__repr__'))
            if name == '__subclasses__':
                return Result(get_guest_builtin('type.__subclasses__'))
            if name == '__dict__':  # Fake it for now.
                return Result({})

        if name == '__eq__':
            return Result(get_guest_builtin('object.__eq__'))
        if name == '__ne__':
            return Result(get_guest_builtin('object.__ne__'))

        if self.name in self.BUILTIN_TYPES:
            if name == '__mro__':
                return Result(self.get_mro())
            if name == '__dict__':  # Fake it for now.
                return Result({})

        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any) -> Any:
        raise NotImplementedError(self, name, value)


@memoize
def get_guest_builtin(name: Text) -> EBuiltin:
    return EBuiltin(name, None)


class EPartial:
    def __init__(self, f: EFunction, args: Tuple[Any, ...]):
        assert isinstance(f, EFunction), f
        self.f = f
        self.args = args

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx) -> Any:
        return self.f.invoke(
            self.args + args, kwargs, locals_dict, ictx)


class NativeFunction(EPyObject):

    def __init__(self, f: Callable[..., Result], name: Text):
        self.f = f
        self.name = name

    def get_type(self) -> EPyObject:
        return EFunctionType.singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any) -> Result[None]:
        raise NotImplementedError

    @check_result
    def invoke(self, *args, **kwargs) -> Result[Any]:
        return self.f(*args, **kwargs)


###################
# Public functions

@check_result
def do_getitem(args: Tuple[Any, ...], ictx: ICtx) -> Result[Any]:
    assert len(args) == 2, args
    o, name = args
    if not isinstance(o, EPyObject):
        return Result(o[name])
    if o.hasattr('__getitem__'):
        f = o.getattr('__getitem__', ictx).get_value()
        return ictx.call(f, (args[1],), {}, {}, globals_=f.globals_)
    raise NotImplementedError(o, name)


@check_result
def do_setitem(args: Tuple[Any, ...], ictx: ICtx) -> Result[None]:
    assert len(args) == 3, args
    log('go:do_setitem()', f'args: {args}')
    o, name, value = args
    if not isinstance(o, EPyObject):
        o[name] = value
        return Result(None)
    if o.hasattr('__setitem__'):
        f = o.getattr('__setitem__', ictx).get_value()
        res = ictx.call(f, (args[1], args[2]), {}, {}, globals_=f.globals_)
        if res.is_exception():
            return res
        return Result(None)
    raise NotImplementedError(o, name)


@check_result
def do_type(args: Tuple[Any, ...], kwargs: Dict[Text, Any]) -> Result[Any]:
    assert not kwargs, kwargs
    assert isinstance(args, tuple), args
    log('go:type()', f'args: {args}')
    if len(args) == 1:
        if isinstance(args[0], EPyObject):
            return Result(args[0].get_type())
        res = type(args[0])
        if res is object:
            return Result(get_guest_builtin('object'))
        if res is type:
            return Result(get_guest_builtin('type'))
        if res is tuple:
            return Result(get_guest_builtin('tuple'))
        return Result(res)

    assert len(args) == 3, args
    name, bases, ns = args

    cls = EClass(name, ns, bases=bases)

    if '__classcell__' in ns:
        ns['__classcell__'].set(cls)
        del ns['__classcell__']

    return Result(cls)


@check_result
def do_hasattr(args: Tuple[Any, ...]) -> Result[bool]:
    assert len(args) == 2, args
    o, attr = args
    assert isinstance(attr, str), attr

    if not isinstance(o, EPyObject):
        r = hasattr(o, attr)
        log('go:hasattr()', f'{o}, {attr} => {r}')
        return Result(r)

    b = o.hasattr(attr)
    assert isinstance(b, bool), b
    return Result(b)


@check_result
def do_getattr(args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
    assert 2 <= len(args) <= 3, args
    assert not kwargs, kwargs
    o, attr, *default = args
    if type(o) is tuple and attr == '__class__':
        return Result(get_guest_builtin('tuple'))
    if not isinstance(o, EPyObject):
        try:
            a = getattr(o, attr, *default)
        except AttributeError as e:
            return Result(ExceptionData(None, None, e))
        else:
            return Result(a)
    if default and not o.hasattr(attr):
        return Result(default[0])
    return o.getattr(attr, ictx)
