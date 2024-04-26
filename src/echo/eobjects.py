import abc
import builtins
import collections
import itertools
import operator
import os
import pprint
import sys
import types
from typing import (
    Text, Any, Dict, Iterable, Tuple, Optional, Set, Callable, Union, Type,
    Deque, List
)
import weakref

from echo.return_kind import ReturnKind
from echo.epy_object import (
    EPyObject, AttrWhere, EPyType, NoContextException, safer_repr, try_invoke,
)
from echo.elog import log, debugged
from echo.interpreter_state import InterpreterState
from echo.interp_context import ICtx
from echo.code_attributes import CodeAttributes
from echo.interp_result import Result, ExceptionData, check_result
from echo.value import Value
from echo.common import memoize

E_PREFIX = 'e' if 'E_PREFIX' not in os.environ else os.environ['E_PREFIX']


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

    def get_type(self) -> EPyType:
        return EFunctionType_singleton

    def __repr__(self):
        return '<{}function {} at {:#x}>'.format(E_PREFIX, self.name, id(self))

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx,
               globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert isinstance(ictx, ICtx), ictx
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
        if name in ('__class__', '__dict__',):
            return AttrWhere.SELF_SPECIAL
        if name in ('__get__',):
            return AttrWhere.CLS
        return None

    def _get(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx,
             globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert len(args) == 3, args
        _self, obj, objtype = args
        assert self is _self
        if obj is None:
            return Result(_self)
        return Result(EMethod(f=_self, bound_self=obj))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__class__':
            return Result(EFunctionType_singleton)
        if name == '__dict__':
            return Result(self.dict_)
        if name == '__closure__':
            return Result(self.closure)
        if name == '__defaults__':
            return Result(self.defaults)
        if name == '__get__':
            return Result(EMethod(NativeFunction(
                self._get, 'efunction.__get__'), bound_self=self))
        if name == '__call__':
            return Result(self)
        try:
            return Result(self.dict_[name])
        except KeyError:
            msg = f'Cannot find attribute {name} on {self}'
            return Result(ExceptionData(None, name, AttributeError(msg)))

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        self.dict_[name] = value
        return Result(None)


class GuestCoroutine(EPyObject):
    def __init__(self, f: EFunction):
        self.f = f

    def get_type(self) -> EPyType:
        return GuestCoroutineType_singleton

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

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError


class EAsyncGeneratorType(EPyType):
    def __init__(self):
        self._dict = {}

    def __repr__(self) -> Text:
        return "<eclass 'async_generator'>"

    def get_name(self) -> str:
        return 'async_generator'

    def get_bases(self): raise NotImplementedError
    def get_dict(self): raise NotImplementedError
    def get_mro(self): raise NotImplementedError

    def get_type(self) -> EPyType:
        return get_guest_builtin('type')

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__mro__':
            return Result((self, get_guest_builtin('type')))
        if name == '__dict__':
            return Result(self._dict)
        raise NotImplementedError(self, name)

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        return None


EAsyncGeneratorType_singleton = EAsyncGeneratorType()


class EAsyncGenerator(EPyObject):
    def __init__(self, f):
        self.f = f

    def get_type(self) -> EPyType:
        return EAsyncGeneratorType_singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError


class EMethodType(EPyType):
    def __repr__(self) -> Text:
        return "<{}class 'method'>".format(E_PREFIX)

    def get_name(self) -> str:
        return 'method'

    def get_bases(self): raise NotImplementedError
    def get_dict(self): raise NotImplementedError
    def get_mro(self): raise NotImplementedError

    def get_type(self) -> EPyType:
        return get_guest_builtin('type')

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None


EMethodType_singleton = EMethodType()


class EMethod(EPyObject):

    def __init__(self, f: Union[EFunction, 'NativeFunction'], bound_self):
        self.f = f
        self.bound_self = bound_self

    def __repr__(self) -> Text:
        return f'<{E_PREFIX}bound method {self.f.name} of {self.bound_self!r}>'

    def get_type(self) -> EPyType:
        return EMethodType_singleton

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
               ictx: ICtx,
               globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert isinstance(args, tuple), args
        return self.f.invoke(
            (self.bound_self,) + args,
            kwargs, locals_dict, ictx, globals_=globals_)


class NotFoundSentinel:
    pass


NotFoundSentinel_singleton = NotFoundSentinel()


def _find_name_in_mro(type_: EPyType, name: Text, ictx: ICtx) -> Any:
    mro = type_.get_mro()
    log('eo:fnim', f'searching for {name} in {mro}')
    for cls in mro:
        if isinstance(cls, EBuiltin):
            if cls.hasattr(name):
                return cls.getattr(name, ictx).get_value()
        elif isinstance(cls, EPyType):
            d = cls.get_dict()
            assert isinstance(d, dict), (cls, d)
            if name in d:
                return d[name]
        else:
            assert isinstance(cls, type), cls
            if hasattr(cls, name):
                return getattr(cls, name)
    return NotFoundSentinel_singleton


def _type_getattro(
        type_: 'EClass', name: Text, ictx: ICtx,
        do_invoke_desc: bool = True) -> Union[Result[Any], Tuple[bool, Any]]:
    assert isinstance(type_, EClass), type_
    if name == '__dict__':
        return Result(type_.dict_)
    if name == '__mro__':
        return Result(type_.get_mro())
    if name == '__class__':
        return Result(type_.metaclass or get_guest_builtin('type'))
    if name == '__bases__':
        return Result(type_.bases)
    if name == '__base__':
        return Result(type_.get_base())
    if name == '__name__':
        return Result(type_.name)

    metatype = type_.get_type()
    meta_attr = _find_name_in_mro(metatype, name, ictx)
    log('eo:ec:ga', f'type_: {type_} name: {name!r} metaclass: {metatype} '
                    f'meta_attr: {meta_attr}')
    if meta_attr is not NotFoundSentinel_singleton:
        if (isinstance(meta_attr, EPyObject)
                and meta_attr.hasattr('__get__')
                and meta_attr.hasattr('__set__')):
            if not do_invoke_desc:
                return (True, meta_attr)
            log('gi:ga', f'overriding descriptor: {meta_attr}')
            f = meta_attr.getattr('__get__', ictx)
            if f.is_exception():
                return f
            v = f.get_value()
            return try_invoke(v, (type_, metatype), {}, {}, ictx)

    attr = _find_name_in_mro(type_, name, ictx)
    if attr is not NotFoundSentinel_singleton:
        log('eo:ec:ga', f'dict attr {name!r} on {type_}: {attr}')
        if isinstance(attr, EPyObject) and attr.hasattr('__get__'):
            if not do_invoke_desc:
                return (True, attr)
            f_result = attr.getattr('__get__', ictx)
            if f_result.is_exception():
                return Result(f_result.get_exception())
            v = f_result.get_value()
            res = try_invoke(v, (None, type_), {}, {}, ictx)
            log('eo:ec:ga', f'invoked descriptor getter {v} => {res}')
            return res
        return Result(attr)

    if meta_attr is not NotFoundSentinel_singleton:
        if (isinstance(meta_attr, EPyObject)
                and meta_attr.hasattr('__get__')):
            log('gi:ga', f'non-overriding descriptor: {meta_attr}')
            if not do_invoke_desc:
                return (True, meta_attr)
            f = meta_attr.getattr('__get__', ictx)
            if f.is_exception():
                return f
            v = f.get_value()
            return try_invoke(v, (type_, metatype), {}, {}, ictx)
        if not do_invoke_desc:
            return (False, meta_attr)
        return Result(meta_attr)

    if metatype.hasattr('__getattr__'):
        meta_ga_ = metatype.getattr('__getattr__', ictx)
        if meta_ga_.is_exception():
            return meta_ga_
        meta_ga = meta_ga_.get_value()
        if meta_ga.hasattr('__get__'):
            if not do_invoke_desc:
                return meta_ga
            meta_ga = invoke_desc(type_, meta_ga, ictx)
            if meta_ga.is_exception():
                return meta_ga
            meta_ga = meta_ga.get_value()
        return try_invoke(meta_ga, (name,), {}, {}, ictx)

    if not do_invoke_desc:
        return (False, None)

    msg = f'Class {type_.name} does not have attribute {name!r}'
    return Result(ExceptionData(
        None,
        None,
        AttributeError(msg)))


class EInstance(EPyObject):

    def __init__(self, cls: Union['EClass', 'EBuiltin']):
        assert isinstance(cls, (EClass, EBuiltin)), cls
        self.cls = cls
        self.dict_: Dict[str, Any] = {}
        self.builtin_storage: Dict[type, Any] = {}

    def __repr__(self) -> Text:
        return '<{} eobject>'.format(self.cls.name)

    def __len__(self):
        raise NotImplementedError

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

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        """Looks up an attribute on this object instance."""
        cls_attr = _find_name_in_mro(self.get_type(), name, ictx)

        log('gi:ga', f'self: {self} name: {name} cls_attr: {cls_attr}')

        if (isinstance(cls_attr, EInstance)
                and cls_attr.hasattr('__get__')
                and cls_attr.hasattr('__set__')):
            log('gi:ga', f'overriding descriptor: {cls_attr}')
            # Overriding descriptor.
            return invoke_desc(self, cls_attr, ictx)

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
            return invoke_desc(self, cls_attr, ictx)

        if cls_attr is not NotFoundSentinel_singleton:
            return Result(cls_attr)

        dunder_getattr = _find_name_in_mro(self.get_type(), '__getattr__',
                                           ictx)
        if dunder_getattr is not NotFoundSentinel_singleton:
            log('eo:ei:ga', f'__getattr__: {dunder_getattr}')
            if (isinstance(dunder_getattr, EPyObject)
                    and dunder_getattr.hasattr('__get__')):
                dunder_getattr = invoke_desc(self, dunder_getattr, ictx)
                if dunder_getattr.is_exception():
                    return dunder_getattr
                dunder_getattr = dunder_getattr.get_value()
            return dunder_getattr.invoke((name,), {}, {}, ictx)

        msg = f"'{self.cls.name}' object does not have attribute {name!r}"
        return Result(ExceptionData(None, None, AttributeError(msg)))

    @check_result
    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        cls_attr: Optional[Any] = None
        if name in self.cls.dict_:
            cls_attr = self.cls.dict_[name]
            log('eo:ei:sa', f'cls_attr {cls_attr!r}')

        if (isinstance(cls_attr, EPyObject)
                and cls_attr.hasattr('__set__')):
            f_result = cls_attr.getattr('__set__', ictx)
            if f_result.is_exception():
                return Result(f_result.get_exception())
            return f_result.get_value().invoke((self, value), {}, {}, ictx)

        self.dict_[name] = value
        return Result(None)

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx,
               globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert isinstance(ictx, ICtx), ictx
        call_res = self.getattr('__call__', ictx)
        if call_res.is_exception():
            return call_res
        call = call_res.get_value()
        return call.invoke(args, kwargs, locals_dict, ictx, globals_=globals_)


def _maybe_builtin(b: Type) -> Union['EBuiltin', Type]:
    if b is Exception:
        return get_guest_builtin('Exception')
    if b is BaseException:
        return get_guest_builtin('BaseException')
    return b


def _get_bases(c: Union[EPyType, Type]) -> Tuple[Union[EPyType, Type], ...]:
    if isinstance(c, type):
        return tuple(_maybe_builtin(b) for b in c.__bases__)
    assert isinstance(c, EPyType), c
    return c.get_bases()


class EClass(EPyType):
    """Represents a user-defined class."""

    def __init__(self, name: Text, dict_: Dict[Text, Any], *,
                 bases: Optional[Tuple[EPyType, ...]] = None,
                 metaclass: Optional[EPyType] = None, kwargs=None):
        self.name = name
        self.dict_ = dict_
        self.bases: Tuple[EPyType, ...] = \
            bases or (get_guest_builtin('object'),)
        self.metaclass: Optional[EPyType] = metaclass
        self.kwargs = kwargs
        self.subclasses: weakref.WeakSet = weakref.WeakSet()

        for base in self.bases:
            if isinstance(base, (EBuiltin, EClass)):
                base.note_subclass(self)

    def get_bases(self) -> Tuple[EPyType, ...]:
        return self.bases

    def get_name(self) -> str:
        return self.name

    def get_dict(self) -> Dict[Text, Any]:
        return self.dict_

    def note_subclass(self, derived: 'EClass') -> None:
        self.subclasses.add(derived)

    def __repr__(self) -> Text:
        if isinstance(self.dict_, dict) and '__module__' in self.dict_:
            return '<{}class \'{}.{}\'>'.format(
                E_PREFIX, self.dict_['__module__'], self.name)
        return '<{}class \'{}\">'.format(E_PREFIX, self.name)

    def get_type(self) -> 'EPyType':
        return self.metaclass or get_guest_builtin('type')

    def get_mro(self) -> Tuple[Union[EPyType, Type], ...]:
        """The MRO is a preorder DFS of the 'derives from' relation."""
        derives_from = []  # (cls, base)
        frontier: Deque[Union[EPyType, Type]] = collections.deque([self])
        while frontier:
            cls = frontier.popleft()
            bases = _get_bases(cls)
            for base in bases:
                derives_from.append((cls, base))
                frontier.append(base)

        cls_to_subclasses_ = collections.defaultdict(list)
        for cls, base in derives_from:
            cls_to_subclasses_[base].append(cls)
        cls_to_subclasses = dict(cls_to_subclasses_)

        ready: Deque[Union[EPyType, Type]] = collections.deque([self])
        order: List[Union[EPyType, Type]] = []

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

    def get_base(self) -> EPyType:
        if len(self.bases) != 1:
            raise NotImplementedError(self, self.bases)
        return self.bases[0]

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx,
               globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert isinstance(ictx, ICtx), ictx
        call_res = self.get_type().getattr('__call__', ictx)
        if call_res.is_exception():
            return call_res
        call = call_res.get_value()
        return call.invoke((self,) + args, kwargs, locals_dict, ictx,
                           globals_=globals_)

    def instantiate(self,
                    args: Tuple[Any, ...],
                    kwargs: Dict[Text, Any],
                    globals_: Dict[Text, Any],
                    ictx: ICtx) -> Result[EInstance]:
        """Creates an instance of this user-defined class."""
        log('eo:ec',
            lambda: f'instantiate self: {self} args: {args} kwargs: {kwargs}')
        guest_instance: Optional[EInstance] = None
        if self.hasattr('__new__'):
            new_f = self.getattr('__new__', ictx).get_value()
            log('eo:ec:new', f'new_f {new_f}')
            result = ictx.call(new_f, (self,) + args, kwargs, locals_dict={},
                               globals_=globals_)
            if result.is_exception():
                return Result(result.get_exception())

            new_guest_instance = result.get_value()
            do_isinstance = get_guest_builtin('isinstance')
            ii_result = do_isinstance.invoke(
                    (new_guest_instance, self), {}, {}, ictx)
            if ii_result.is_exception():
                return ii_result
            assert isinstance(ii_result.get_value(), bool), \
                ii_result.get_value()
            if not ii_result.get_value():
                return Result(new_guest_instance)
            guest_instance = new_guest_instance
        guest_instance = (EInstance(self) if guest_instance is None
                          else guest_instance)
        if self.hasattr('__init__'):
            init_f = self.getattr('__init__', ictx).get_value()
            # TODO(cdleary, 2019-01-26) What does Python do when you return
            # something non-None from initializer? Ignore?
            assert isinstance(guest_instance, EPyObject), guest_instance
            init_res = ictx.call(
                init_f, (guest_instance,) + args, kwargs, {},
                globals_=globals_)
            if init_res.is_exception():
                return Result(init_res.get_exception())
        return Result(guest_instance)

    @debugged('eo:ec:hasattr_where()')
    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict_:
            return AttrWhere.SELF_DICT
        if name in ('__class__', '__bases__', '__base__', '__mro__',
                    '__dict__', '__name__'):
            return AttrWhere.SELF_SPECIAL
        if self.get_type().hasattr(name):
            return AttrWhere.CLS
        for base in self.get_mro()[1:]:
            assert isinstance(base, EPyObject)
            haw = base.hasattr_where(name)
            if haw:
                return haw

        return None

    @debugged('eo:ec:ga')
    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        """Looks up an attribute on this class object.

        This should effectively correspond to type_getattro.
        """
        r = _type_getattro(self, name, ictx)
        assert isinstance(r, Result)
        return r

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        sa = _find_name_in_mro(self.get_type(), '__setattr__', ictx)
        if (sa is NotFoundSentinel_singleton
                or sa is get_guest_builtin('object.__setattr__')):
            self.dict_[name] = value
            log('eo:ec:setattr',
                f'updated self.dict_ {self.dict_} name {name} value {value}')
            return Result(None)
        log('eo:ec:setattr',
            f'self {self} name {name} value {value} => invoking {sa}')
        return sa.invoke((self, name, value), {}, {}, ictx)


class EFunctionType(EPyType):
    def __repr__(self) -> Text:
        return "<{}class 'function'>".format(E_PREFIX)

    def get_name(self) -> str: return 'function'

    def get_type(self) -> EPyType:
        return get_guest_builtin('type')

    def get_bases(self):
        raise NotImplementedError

    def get_dict(self):
        # TODO: return mapping proxy
        return {}

    def get_mro(self) -> Tuple[EPyType, ...]:
        return (self,)

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__code__', '__globals__', '__get__'):
            return AttrWhere.SELF_SPECIAL
        return None

    def _get_desc(self, args, kwargs: Dict[Text, Any],
                  locals_dict: Dict[Text, Any],
                  ictx: ICtx,
                  globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert not kwargs, kwargs
        assert len(args) == 3, args
        eself, obj, objtype = args
        if obj is None:
            return Result(eself)
        return Result(EMethod(eself, bound_self=obj))

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name in ('__code__', '__globals__'):
            return Result(None)

        if name == '__get__':
            return Result(NativeFunction(self._get_desc, 'efunction.__get__'))

        raise NotImplementedError

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError


EFunctionType_singleton = EFunctionType()


class GuestCoroutineType(EPyType):

    def __init__(self):
        self.dict_ = {}

    def get_name(self) -> str:
        return 'coroutine'

    def __repr__(self) -> Text:
        return "<eclass 'coroutine'>"

    def get_bases(self):
        raise NotImplementedError

    def get_dict(self):
        raise NotImplementedError

    def get_mro(self) -> Tuple[EPyType, ...]:
        return (self, get_guest_builtin('type'))

    def get_type(self) -> EPyType:
        return get_guest_builtin('type')

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in ('__mro__', '__dict__'):
            return AttrWhere.SELF_SPECIAL
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__mro__':
            return Result(self.get_mro())
        if name == '__dict__':
            return Result(self.dict_)
        raise NotImplementedError(name)

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError(name, value)


GuestCoroutineType_singleton = GuestCoroutineType()


def _is_type_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'type'


def _is_dict_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'dict'


def _is_int_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'int'


def _is_bool_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'bool'


def is_list_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'list'


def _is_object_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'object'


def _is_exception_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'Exception'


def _is_base_exception_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'BaseException'


def _is_str_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'str'


def is_tuple_builtin(x) -> bool:
    return isinstance(x, EBuiltin) and x.name == 'tuple'


@check_result
def _do_len(
        args: Tuple[Any, ...],
        ictx: ICtx) -> Result[Any]:
    assert len(args) == 1
    if not isinstance(args[0], EPyObject):
        return Result(len(args[0]))
    do_len_ = args[0].getattr('__len__', ictx)
    if do_len_.is_exception():
        return do_len_
    do_len = do_len_.get_value()
    res: Result[Any] = do_len.invoke((), {}, {}, ictx)
    if res.is_exception():
        return res
    v = res.get_value()
    assert isinstance(v, int)  # For now.
    if v < 0:
        return Result(ExceptionData(
            None, None, ValueError('__len__() should return >= 0')))
    return Result(v)


class EBuiltin(EPyType):
    """A builtin function/type in the echo VM."""

    BUILTIN_TYPES = (
        'object', 'type', 'classmethod', 'bytearray', 'bytes',
        'staticmethod', 'property', 'Exception', 'super', 'enumerate', 'map',
        'str', 'dict', 'tuple', 'list', 'int', 'bool', 'BaseException',
    )
    BUILTIN_FNS = (
        'len', '__build_class__', 'getattr', 'setattr', 'iter', 'reversed',
        'zip', 'next', 'repr', 'exec', 'hash', 'vars', 'dir', 'sum',
        'isinstance', 'issubclass', 'hasattr', 'any', 'min', 'max', 'callable',
        # object
        'object.__new__', 'object.__init__',
        'object.__str__',
        'object.__repr__',
        'object.__setattr__',
        'object.__format__', 'object.__reduce_ex__',
        'object.__ne__', 'object.__eq__',
        'object.__subclasshook__',
        # type
        'type.__new__', 'type.__init__',
        'type.__str__', 'type.__repr__',
        'type.__subclasses__',
        'type.mro', 'type.__call__',
        # str
        'str.maketrans', 'str.join', 'str.__repr__',
        # dict
        'dict.__eq__', 'dict.__init__', 'dict.__repr__',
        'dict.__setitem__', 'dict.__getitem__', 'dict.__delitem__',
        'dict.__contains__',
        'dict.fromkeys', 'dict.update', 'dict.setdefault',
        'dict.pop', 'dict.get',
        # int
        'int.__new__', 'int.__init__',
        'int.__add__', 'int.__radd__',
        'int.__sub__', 'int.__rsub__',
        'int.__and__', 'int.__rand__',
        'int.__mul__', 'int.__rmul__',
        'int.__bool__', 'int.__repr__', 'int.__str__', 'int.__int__',
        # int cmp
        'int.__eq__', 'int.__ne__', 'int.__lt__', 'int.__ge__', 'int.__le__',
        'int.__gt__',
        # list
        'list.__new__', 'list.__init__',
        'list.__eq__', 'list.__repr__',
        'list.append', 'list.extend', 'list.clear', 'list.remove',
        'list.__contains__', 'list.__iter__', 'list.__getitem__',
        'list.__setitem__',
        # tuple
        'tuple.__new__', 'tuple.__init__',
        'tuple.__eq__', 'tuple.__lt__',
        'tuple.__getitem__', 'tuple.__repr__',
        # bytearray
        'bytearray.__setitem__', 'bytearray.__repr__',
    )

    _registry: Dict[Text, Tuple[Callable, Optional[type]]] = {}

    def __init__(self, name: Text, bound_self: Any, singleton_ok: bool = True):
        self.name = name
        self.bound_self = bound_self
        self.dict_: Dict[Text, Any] = {}
        self.globals_: Dict[Text, Any] = {}

    def get_name(self) -> str:
        return 'builtin_type'

    def has_standard_getattr(self) -> bool:
        if self.name in ('super',):
            return False
        return True

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

    def __repr__(self) -> Text:
        if self.name in self.BUILTIN_TYPES:
            return "<{}class '{}'>".format(E_PREFIX, self.name)
        if self.name in self.BUILTIN_FNS and not self.bound_self:
            return f'<{E_PREFIX}built-in function {self.name}>'
        return 'EBuiltin(name={!r}, bound_self={!r}, ...)'.format(
            self.name, self.bound_self)

    def get_dict(self):
        raise NotImplementedError

    def get_bases(self):
        if self.name == 'object':
            return ()
        eobject = get_guest_builtin('object')
        if self.name == 'Exception':
            return (get_guest_builtin('BaseException'),)
        return (eobject,)

    def get_type(self) -> EPyType:
        if self.name in self.BUILTIN_FNS:
            if self.bound_self:
                return EMethodType_singleton
            else:
                return EFunctionType_singleton
        if self.name in self.BUILTIN_TYPES:
            return get_guest_builtin('type')
        raise NotImplementedError(self)

    def get_mro(self) -> Tuple[EPyType, ...]:
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
        if self is other:
            return True
        return False

    @check_result
    def invoke(self,
               args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               locals_dict: Dict[Text, Any],
               ictx: ICtx,
               globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert isinstance(ictx, ICtx), ictx
        if self.name == 'zip':
            return Result(zip(*args))
        if self.name == 'reversed':
            return Result(reversed(*args))
        if self.name == 'chr':
            return Result(chr(*args))
        if self.name == 'len':
            return _do_len(args, ictx)
        if self.name == 'hasattr':
            return do_hasattr(args, ictx)
        if self.name == 'dir':
            if not args and not kwargs:
                if locals_dict is not None:
                    return Result(list(locals_dict.keys()))
                assert globals_ is not None
                return Result(list(globals_.keys()))
            return _do_dir(args, kwargs, ictx)
        if self.name == 'vars':
            if len(args) == 0 and not kwargs:
                return Result(locals_dict)
            return _do_vars(args, kwargs, ictx)
        if self.name == 'getattr':
            return do_getattr(args, kwargs, ictx)
        if self.name == 'setattr':
            return do_setattr(args, kwargs, ictx)
        if self.name == 'type.__call__':
            if self.bound_self is not None:
                args = (self.bound_self,) + args
            return self._registry[self.name][0](args, kwargs, globals_, ictx)

        # Check if the builtin has been registered from an external location.
        if self.name in self._registry:
            if self.bound_self is not None:
                args = (self.bound_self,) + args
            return self._registry[self.name][0](args, kwargs, ictx)

        raise NotImplementedError(
                'Did not find {!r} in {!r}'.format(self.name,
                                                   self._registry.keys()))

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        if name in self.dict_:
            return AttrWhere.SELF_DICT
        if (self.name in self.BUILTIN_TYPES
                and f'{self.name}.{name}' in self.BUILTIN_FNS):
            return AttrWhere.SELF_SPECIAL
        if self.name == 'str' and name in ('maketrans',):
            return AttrWhere.SELF_SPECIAL
        if (self.name in self.BUILTIN_TYPES
                and name in ('__mro__', '__dict__',)):
            return AttrWhere.SELF_SPECIAL
        if self.name in self.BUILTIN_FNS and name == '__get__':
            return AttrWhere.CLS
        if (self.name in self.BUILTIN_TYPES
                and name in ('__new__', '__init__', '__dict__', '__str__',
                             '__repr__', '__eq__', '__ne__', '__new__',
                             '__name__')):
            return AttrWhere.SELF_SPECIAL
        if self.name == 'object' and name in (
                '__subclasshook__', '__bases__', '__setattr__', '__repr__',):
            return AttrWhere.SELF_SPECIAL
        if self.name == 'type' and name in ('__subclasses__', 'mro',
                                            '__call__', '__repr__',):
            return AttrWhere.SELF_SPECIAL
        if name == '__eq__':
            return AttrWhere.CLS
        return None

    @debugged('eo:ebi')
    def _get(self,
             args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             locals_dict: Dict[Text, Any],
             ictx: ICtx,
             globals_: Optional[Dict[Text, Any]] = None) -> Result[Any]:
        assert len(args) == 3, args
        _self, obj, objtype = args
        assert self is _self
        if obj is None:
            return Result(_self)
        return Result(EMethod(f=_self, bound_self=obj))

    @check_result
    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        if name == '__self__' and self.bound_self is not None:
            return Result(self.bound_self)

        if self.name in self.BUILTIN_TYPES:
            if name == '__module__':
                return Result('builtins')
            if name == '__bases__':
                return Result(self.get_bases())

        if (self.name in self.BUILTIN_TYPES and
                name in ('__name__', '__qualname__')):
            return Result(self.name)

        if self.name in self.BUILTIN_TYPES and name in ('__doc__'):
            return Result(getattr(builtins, self.name).__doc__)

        if (self.name in self.BUILTIN_TYPES
                and name in ('__annotations__',)):
            return Result(ExceptionData(
                None, None, AttributeError('__annotations__')))

        if self.name in self.BUILTIN_TYPES:
            fullname = f'{self.name}.{name}'
            if fullname in self.BUILTIN_FNS:
                return Result(get_guest_builtin(fullname))

        if self.name == 'int':
            if name == '__dict__':
                return Result({
                    '__new__': get_guest_builtin('int.__new__'),
                    '__repr__': get_guest_builtin('int.__repr__'),
                })

        if self.name == 'Exception':
            if name == '__new__':
                return Result(get_guest_builtin('Exception.__new__'))
            if name == '__init__':
                return Result(get_guest_builtin('Exception.__init__'))

        if self.name == 'dict':
            if name == '__new__':
                return Result(get_guest_builtin('dict.__new__'))
            if name == '__dict__':
                return Result({
                    'fromkeys': get_guest_builtin('dict.fromkeys'),
                })

        if (self.name in self.BUILTIN_FNS
                and name == '__get__'):
            return Result(EMethod(NativeFunction(
                self._get, 'ebuiltin.__get__'), bound_self=self))

        if (self.name in self.BUILTIN_FNS
                and name == '__call__'):
            return Result(self)

        if self.name == 'object':
            if name == '__format__':
                return Result(get_guest_builtin('object.__format__'))
            if name == '__reduce_ex__':
                return Result(get_guest_builtin('object.__reduce_ex__'))
            if name == '__subclasshook__':
                return Result(get_guest_builtin('object.__subclasshook__'))
            if name == '__bases__':
                return Result(())
            if name == '__dict__':  # Fake it for now.
                return Result({})

        if self.name == 'type':
            if name == '__name__':
                return Result(get_guest_builtin('type.__name__'))
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

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Any:
        raise NotImplementedError(self, name, value)


def register_builtin(
        name: Text,
        type_: Optional[type] = None) -> Callable[[Callable], Callable]:
    def fregister(f: Callable) -> Callable:
        EBuiltin.register(name, f, type_)
        return f
    return fregister


@memoize
def get_guest_builtin(name: Text) -> EBuiltin:
    return EBuiltin(name, None)


def get_guest_builtin_self(name: Text, self: Any) -> EBuiltin:
    return EBuiltin(name, self)


class NativeFunction(EPyObject):

    def __init__(self, f: Callable[..., Result], name: Text):
        self.f = f
        self.name = name

    def __repr__(self) -> Text:
        return f'<built-in function {self.name}>'

    def get_type(self) -> EPyType:
        return EFunctionType_singleton

    def hasattr_where(self, name: Text) -> Optional[AttrWhere]:
        return None

    def getattr(self, name: Text, ictx: ICtx) -> Result[Any]:
        raise NotImplementedError

    def setattr(self, name: Text, value: Any, ictx: ICtx) -> Result[None]:
        raise NotImplementedError

    @check_result
    def invoke(self, *args, **kwargs) -> Result[Any]:
        return self.f(*args, **kwargs)


@check_result
def _do_dir(args: Tuple[Any, ...],
            kwargs: Dict[Text, Any],
            ictx: ICtx) -> Result[Any]:
    assert len(args) == 1, args
    o = args[0]
    if isinstance(o, EPyObject):
        d_result = o.getattr('__dict__', ictx)
        if d_result.is_exception():
            return Result(d_result.get_exception())
        d: Dict[Text, Any] = d_result.get_value()
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
    log('eo:do_setitem()', f'args: {args}')
    o, name, value = args
    hsi = do_hasattr((o, '__setitem__'), ictx).get_value()
    if hsi:
        f = do_getattr((o, '__setitem__'), {}, ictx).get_value()
        res = ictx.call(f, (name, value), {}, {})
        if res.is_exception():
            return res
        return Result(None)
    raise NotImplementedError(o, name, value)


@check_result
def do_delitem(args: Tuple[Any, ...], ictx: ICtx) -> Result[None]:
    assert len(args) == 2, args
    log('eo:do_delitem()', f'args: {args}')
    o, name = args
    if not isinstance(o, EPyObject):
        del o[name]
        return Result(None)
    if o.hasattr('__delitem__'):
        f = o.getattr('__delitem__', ictx).get_value()
        res = ictx.call(f, (args[1],), {}, {}, globals_=f.globals_)
        if res.is_exception():
            return res
        return Result(None)
    raise NotImplementedError(o, name)


@check_result
def do_hasattr(args: Tuple[Any, ...], ictx: ICtx) -> Result[bool]:
    assert len(args) == 2, args
    o, attr = args
    assert isinstance(attr, str), attr

    if not isinstance(o, EPyObject):
        b = hasattr(o, attr)
        log('eo:hasattr()', lambda: f'{o}, {attr} => {b}')
        return Result(b)

    r: Result[Any] = o.getattr(attr, ictx)
    log('eo:hasattr()', lambda: f'o {o} attr {attr!r} getattr result: {r}')
    if r.is_exception():
        if isinstance(r.get_exception().exception, AttributeError):
            return Result(False)
        return Result(r.get_exception())

    return Result(True)


@check_result
def do_getattr(args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
    assert 2 <= len(args) <= 3, args
    assert not kwargs, kwargs
    o, attr, *default = args
    # TODO(cdleary): 2020-01-01 genericize this
    if type(o) is tuple and attr == '__class__':
        return Result(get_guest_builtin('tuple'))
    if o is TypeError and attr == '__bases__':
        return Result((get_guest_builtin('Exception'),))
    if o is None and attr == '__new__':
        return Result(get_guest_builtin('type.__new__'))

    clsname = o.__class__.__name__
    if (type(o) in (int, str, tuple, list, bytearray)
            and f'{clsname}.{attr}' in EBuiltin.BUILTIN_FNS):
        return Result(get_guest_builtin_self(f'{clsname}.{attr}', o))
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


@check_result
def do_setattr(args: Tuple[Any, ...],
               kwargs: Dict[Text, Any],
               ictx: ICtx) -> Result[Any]:
    assert isinstance(args, tuple), args
    assert len(args) == 3, args
    assert not kwargs, kwargs
    obj, name, value = args
    if isinstance(obj, EPyObject):
        res = obj.setattr(name, value, ictx=ictx)
        if res.is_exception():
            return res
        return Result(None)
    elif obj is sys and name == 'path':
        sys.path = ictx.interp_state.paths = value
        return Result(None)
    else:
        setattr(obj, name, value)
        return Result(None)


@check_result
def invoke_desc(self, cls_attr: EPyObject, ictx: ICtx) -> Result[Any]:
    assert cls_attr.hasattr('__get__')

    # Grab the descriptor getter off the descriptor.
    f_result = cls_attr.getattr('__get__', ictx)
    if f_result.is_exception():
        return Result(f_result.get_exception())
    f = f_result.get_value()

    # Determine the type of obj.
    do_type = get_guest_builtin('type')
    objtype_result = do_type.invoke(args=(cls_attr,), kwargs={},
                                    locals_dict={}, ictx=ictx)
    if objtype_result.is_exception():
        return Result(objtype_result.get_exception())
    objtype = objtype_result.get_value()

    ictx.desc_count += 1

    return f.invoke((self, objtype), {}, {}, ictx)


@check_result
def _do_vars(args: Tuple[Any, ...],
             kwargs: Dict[Text, Any],
             ictx: ICtx) -> Result[Any]:
    assert len(args) == 1
    return do_getattr((args[0], '__dict__'), {}, ictx)
