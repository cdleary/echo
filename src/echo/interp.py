"""(Metacircular) interpreter loop implementation."""

import abc
import builtins
import collections
import dis
import functools
import logging
import operator
import os
import types
import weakref
import sys

from io import StringIO
from typing import (
    Dict, Any, Text, Tuple, List, Optional, Union, Sequence, Iterable, cast,
    Callable,
)

from echo.common import dis_to_str, get_code
from echo.elog import log, ECHO_DEBUG
from echo.interp_result import Result, ExceptionData, check_result
from echo.interp_context import ICtx
from echo import import_routines
from echo.arg_resolver import resolve_args
from echo import code_attributes
from echo.interpreter_state import InterpreterState
from echo.guest_objects import (
    GuestFunction, GuestInstance, GuestBuiltin, GuestPyObject,
    GuestPartial, GuestClass, GuestCell, GuestMethod, GuestGenerator,
    GuestAsyncGenerator, ReturnKind, GuestTraceback, GuestProperty,
    GuestClassMethod, NativeFunction
)
from echo.guest_module import GuestModule
from echo import interp_routines
from echo.frame_objects import StatefulFrame, UnboundLocalSentinel
from echo.value import Value


@check_result
def interp(code: types.CodeType,
           *,
           globals_: Dict[Text, Any],
           ictx: ICtx,
           name: Text,
           locals_dict: Optional[Dict[Text, Any]] = None,
           args: Optional[Tuple[Any, ...]] = None,
           kwargs: Optional[Dict[Text, Any]] = None,
           defaults: Optional[Tuple[Any, ...]] = None,
           kwarg_defaults: Optional[Dict[Text, Any]] = None,
           closure: Optional[Tuple[GuestCell, ...]] = None,
           in_function: bool = True) -> Result[Any]:
    """Evaluates "code" using "globals_" after initializing locals with "args".

    Returns the result of evaluating the code object.

    Args:
        code: Code object to interpret.
        globals_: Global mapping to use (for global references).
        args: Arguments to populate local variables with (for a function
            invocation).
        defaults: Default arguments to use if the arguments haven't been
            populated via invocation.
        in_function: Whether this code is being interpreted at function scope;
            this controls whether generic "name" references resolve against
            globals (vs function locals).

    Implementation note: this is one giant function for the moment, unclear
    whether performance will be important, but this makes it easy for early
    prototyping.

    TODO(cdleary): 2019-01-21 Use dis.stack_effect to cross-check stack depth
        change.
    """
    log('interp', f'args: {args} kwargs: {kwargs}')

    closure = closure or ()

    assert len(code.co_freevars) == len(closure), (
        'Invocation did not satisfy closure requirements.', code,
        code.co_freevars, closure)

    def gprint(*args): interp_routines.cprint(*args, color='green')

    # Set up arguments as a precursor to establishing the locals.
    attrs = code_attributes.CodeAttributes.from_code(code, name)
    arg_result = resolve_args(
        attrs, args, kwargs, defaults, kwarg_defaults)
    if arg_result.is_exception():
        return Result(arg_result.get_exception())

    arg_locals, additional_local_count = arg_result.get_value()

    locals_ = (arg_locals + [UnboundLocalSentinel] * additional_local_count)
    cellvars = tuple(GuestCell(name) for name in code.co_cellvars) + closure

    # Cellvars that match argument names get populated with the argument value,
    # and it seems as though locals_ for that value is never referenced in the
    # bytecode.
    for i, cellvar_name in enumerate(code.co_cellvars):
        try:
            index = code.co_varnames.index(cellvar_name)
        except ValueError:
            continue
        else:
            local_value = locals_[index]
            cellvars[i].set(local_value)

    if ECHO_DEBUG:
        log('interp:ci', dis.code_info(code))
        # TODO(cdleary): 2019-11-20 Re-enable this in a logging channel.
        # dis.dis(code, file=sys.stderr)

    instructions = tuple(dis.get_instructions(code))
    pc_to_instruction = [None] * (instructions[-1].offset+1)
    pc_to_bc_width = [None] * (instructions[-1].offset+1)
    for i, instruction in enumerate(instructions):
        pc_to_instruction[instruction.offset] = instruction
        if i+1 != len(instructions):
            pc_to_bc_width[instruction.offset] = (
                instructions[i+1].offset-instruction.offset)
    del instructions

    f = StatefulFrame(code, pc_to_instruction, pc_to_bc_width, locals_,
                      locals_dict, globals_, cellvars, in_function, ictx)

    if attrs.generator:
        return Result(GuestGenerator(f))

    if attrs.async_generator:
        return Result(GuestAsyncGenerator(f))

    result = f.run_to_return_or_yield()
    if result.is_exception():
        return Result(result.get_exception())

    v, kind = result.get_value()
    assert kind == ReturnKind.RETURN, kind
    assert isinstance(v, Value), v
    return Result(v.wrapped)


@check_result
def _do_call_functools_partial(
        args: Tuple[Any, ...],
        kwargs: Optional[Dict[Text, Any]]) -> Result[Any]:
    """Helper for calling `functools.partial`."""
    if kwargs:
        raise NotImplementedError(kwargs)
    guest_partial = GuestPartial(args[0], args[1:])
    return Result(guest_partial)


@check_result
def _do_call_property(
        args: Tuple[Any, ...],
        kwargs: Optional[Dict[Text, Any]]) -> Result[Any]:
    if kwargs:
        raise NotImplementedError(kwargs)
    if len(args) != 1:
        raise NotImplementedError(args)
    guest_property = GuestProperty(args[0])
    return Result(guest_property)


def _do_call_classmethod(
        args: Tuple[Any, ...],
        kwargs: Optional[Dict[Text, Any]]) -> Result[Any]:
    if len(args) != 1 or kwargs:
        raise NotImplementedError(args, kwargs)
    return Result(GuestClassMethod(args[0]))


@check_result
def _do_call_getattr(
        args: Tuple[Any, ...],
        kwargs: Optional[Dict[Text, Any]],
        ictx: ICtx,
        ) -> Result[Any]:
    assert len(args) in (2, 3), args
    log('interp:dcga', f'args: {args} kwargs: {kwargs}')

    if not isinstance(args[0], GuestPyObject):
        return Result(getattr(*args))

    if not args[0].hasattr(args[1]):
        if len(args) == 3:
            return Result(args[2])
        return Result(ExceptionData(
            None, None,
            AttributeError(f"object has no attribute {args[1]!r}")))

    return args[0].getattr(args[1], ictx)


@check_result
def do_call(f,
            args: Tuple[Any, ...],
            kwargs: Dict[Text, Any],
            locals_dict: Dict[Text, Any],
            *,
            ictx: ICtx,
            globals_: Dict[Text, Any],
            get_exception_data: Optional[
                Callable[[], Optional[ExceptionData]]] = None,
            in_function: bool = True
            ) -> Result[Any]:
    log('interp:do_call', f'f: {f} kwargs: {kwargs}')

    assert in_function

    kwargs = kwargs or {}
    if f in (dict, chr, range, print, sorted, str, set, tuple, list, hasattr,
             bytearray, object, frozenset, weakref.WeakSet,
             weakref.ref) + interp_routines.BUILTIN_EXCEPTION_TYPES:
        return Result(f(*args, **kwargs))

    if f is sys.exc_info:
        exception_data = get_exception_data()
        if exception_data is None:
            return Result(None)
        tb, p, exc = (exception_data.traceback, exception_data.parameter,
                      exception_data.exception)
        t = GuestTraceback(tuple(tb))
        return Result((exc, p, t))
    if f is globals:
        return Result(globals_)
    elif isinstance(f, (GuestFunction, GuestMethod, GuestClassMethod,
                        NativeFunction)):
        return f.invoke(args, kwargs, locals_dict, ictx)
    elif isinstance(f, (types.MethodType, types.FunctionType)):
        # Builtin object method.
        return Result(f(*args, **kwargs))
    # TODO(cdleary, 2019-01-22): Consider using an import hook to avoid
    # the C-extension version of functools from being imported so we
    # don't need to consider it specially.
    elif f is functools.partial:
        return _do_call_functools_partial(args, kwargs)
    elif f is property:
        return _do_call_property(args, kwargs)
    elif f is classmethod:
        return _do_call_classmethod(args, kwargs)
    elif f is getattr:
        return _do_call_getattr(
            args=args, kwargs=kwargs, ictx=ictx)
    elif isinstance(f, GuestPartial):
        return f.invoke(args, kwargs, locals_dict, ictx)
    elif isinstance(f, GuestBuiltin):
        return f.invoke(args, kwargs, locals_dict, ictx)
    elif isinstance(f, GuestClass):
        return f.instantiate(args, kwargs, globals_=globals_, ictx=ictx)
    elif callable(f):
        return Result(f(*args, **kwargs))
    else:
        if isinstance(f, GuestPyObject):
            type_name = f.get_type().name
        else:
            type_name = type(f).__name__
        return Result(ExceptionData(
            None, None,
            TypeError(f"'{type_name}' object {f} is not callable")))


def run_function(f: types.FunctionType, *args: Tuple[Any, ...],
                 globals_: Optional[Dict[Text, Any]] = None) -> Any:
    """Interprets f in the echo interpreter, returns unwrapped result."""
    state = InterpreterState(script_directory=None)
    globals_ = globals_ or globals()
    ictx = ICtx(state, interp, do_call)
    result = interp(get_code(f), globals_=globals_, defaults=f.__defaults__,
                    args=args, name=f.__name__, ictx=ictx)
    return result.get_value()


def import_path(path: Text, module_name: Text, fully_qualified_name: Text,
                ictx: ICtx) -> Result[import_routines.ModuleT]:
    result = import_routines.import_path(
        path, module_name, fully_qualified_name, ictx)
    return result
