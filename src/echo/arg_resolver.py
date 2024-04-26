"""Helpers for resolving given args/kwargs to frame slots."""

from typing import Dict, Optional, Tuple, Any, List, Sequence

import pprint
import sys
import types

from echo.interp_result import Result, ExceptionData, check_result
from echo import code_attributes
from echo.elog import log

from termcolor import cprint


def _arg_join(arg_names: Sequence[str]) -> str:
    if len(arg_names) == 1:
        return "'{}'".format(arg_names[0])
    pieces = []
    for name in arg_names:
        pieces.append("'{}'".format(name))
    s = ', '.join(pieces[:-1])
    return s + ', and ' + pieces[-1]


class _Sentinel:
    """Used to ensure we fill in all argument slots."""


@check_result
def resolve_args(
        attrs: code_attributes.CodeAttributes,
        args: Optional[Tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        defaults: Optional[Tuple[Any, ...]] = None,
        kwarg_defaults: Optional[Dict[str, Any]] = None
        ) -> Result[Tuple[List[Any], int]]:
    """Returns argument prefix that is pre-pended to local slots of a frame."""
    args = args or ()
    kwargs = kwargs or {}
    defaults = defaults or ()
    kwarg_defaults = kwarg_defaults or {}

    # The relevant information provided by attrs is:
    #   argcount        required positional argument count
    #   total_argcount  total number of argument slots (sans *kwargs)
    #                   (if there are *args it is total_argcount-1 in the
    #                    arg_slots)
    #   starargs        i.e. *args
    #   starkwargs      i.e. **kwargs
    #   varnames        names of the arguments as in their definition signature
    #   kwonlyargcount  number of names after the '*' position

    log('ar', f'code: {attrs.code}')
    log('ar', lambda: f'args: {args}')
    log('ar:attrs', f'argcount:       {attrs.argcount}')
    log('ar:attrs', f'total_argcount: {attrs.total_argcount}')
    log('ar:attrs', f'kwonlyargcount: {attrs.kwonlyargcount}')
    log('ar:attrs', f'starargs:       {attrs.starargs}')
    log('ar:attrs', f'starkwargs:     {attrs.starkwargs}')
    log('ar:attrs', f'varnames:       {attrs.varnames}')
    log('ar:attrs', f'defaults:       {defaults}')
    log('ar:attrs', f'kwarg_defaults: {kwarg_defaults}')

    # The functionality of this method is to populate these arg slots
    # appropriately.
    arg_slots: List[Any] = [_Sentinel] * attrs.total_argcount

    if attrs.starargs:
        # Note: somewhat surprisingly, the arg slot for the varargs doesn't
        # live at its corresponding syntactical position in the argument list;
        # instead, Python appears to put it as the last argument, always.
        stararg_index: Optional[int] = attrs.stararg_index
        assert stararg_index is not None
        arg_slots[stararg_index] = ()
    else:
        permitted_args = attrs.total_argcount_no_skwa - attrs.kwonlyargcount
        log('ar', f'given args: {len(args)} permitted: {permitted_args}')
        if len(args) > permitted_args:
            msg = '{}() takes {} positional arguments but {} {} given'.format(
                    attrs.name, permitted_args, len(args),
                    'was' if len(args) == 1 else 'were')
            log('ar', 'emsg: ' + msg)
            return Result(ExceptionData(
                traceback=None,
                parameter=None,
                exception=TypeError(msg)))

    starkwarg_index: Optional[int] = None
    if attrs.starkwargs:
        starkwarg_index = attrs.starkwarg_index
        assert starkwarg_index is not None
        arg_slots[starkwarg_index] = {}

    # Check for keyword-only arguments that were not provided.
    if attrs.kwonlyargcount:
        start, limit = (attrs.total_argcount_no_skwa-attrs.kwonlyargcount,
                        attrs.total_argcount_no_skwa)
        if attrs.starargs:
            start -= 1
            limit -= 1
        kwonly_names = attrs.varnames[start:limit]
        missing = []
        for name in kwonly_names:
            if name not in kwargs and name not in kwarg_defaults:
                missing.append(name)
        if missing:
            msg = 'missing {} required keyword-only argument{}: {}'.format(
                len(missing), 's' if len(missing) != 1 else '',
                _arg_join(missing))
            log('ar', 'emsg: ' + msg)
            return Result(ExceptionData(
                traceback=None,
                parameter=None,
                exception=TypeError(msg)))

    # Note the name of each slot.
    arg_names = attrs.varnames[:len(arg_slots)]

    # Keep track of whether it should be populated by a default value, and if
    # so, what index default value should be used.
    #
    # For example:
    #       def f(a, b=2, c=3): ...
    #
    # Will produce the following "default required" array:
    #
    #       [None, 0, 1]
    #
    # If we find we have a kwarg that populates a slot like "c", we set the
    # "default required" annotation to None:
    #
    #       f(42, c=7) => default_required: [None, 0, None]
    default_required: List[Optional[int]] = \
        [None] * attrs.total_argcount_no_skwa
    if defaults:
        start = attrs.total_argcount_no_skwa-len(defaults)-len(kwarg_defaults)
        limit = attrs.total_argcount_no_skwa-len(kwarg_defaults)
        default_required[start:limit] = list(range(len(defaults)))

    def in_stararg_position(argno: int) -> Tuple[bool, int]:
        # Determines whether the positional argument 'argno' provided by the
        # caller should populate the starargs value or just fill in a normal
        # argument slot.
        if attrs.starargs:
            needed_at_start = attrs.argcount
            if argno < needed_at_start:
                return (False, argno)
            assert stararg_index is not None
            return (True, stararg_index)
        return (False, argno)

    def populate_positional(argno: int, value: Any) -> None:
        assert len(default_required) == attrs.total_argcount_no_skwa, \
            (default_required, attrs.total_argcount_no_skwa)
        stararg_info = in_stararg_position(argno)
        argno = stararg_info[1]  # Stararg can update the slot index.
        if stararg_info[0]:
            assert stararg_index is not None
            arg_slots[stararg_index] = arg_slots[stararg_index] + (value,)
        else:
            assert argno < len(arg_slots), (
                'Argument number is out of range of argument slots.', argno,
                attrs, getattr(attrs, 'code', None), value)
            log('ar', lambda: f'updating arg_slots[{argno}] = {value!r}')
            arg_slots[argno] = value
            default_required[argno] = None

    # Populate the positionally-passed arguments.
    for argno, arg in enumerate(args):
        populate_positional(argno, arg)

    # Populate the keyword arguments.
    all_kwargs = dict(kwarg_defaults)
    log('ar', lambda: f'kwarg defaults: {all_kwargs}')
    all_kwargs.update(kwargs)
    log('ar', lambda: f'all kwargs:     {all_kwargs}')
    for kw, arg in all_kwargs.items():
        # Resolve the keyword to an index.
        try:
            index = arg_names.index(kw)
        except ValueError:
            if starkwarg_index is not None:
                star_kwargs = arg_slots[starkwarg_index]
                assert isinstance(star_kwargs, dict)
                star_kwargs[kw] = arg
                continue
            print('attempted to resolve keyword:  ', kw, file=sys.stderr)
            print('against arg_names:', arg_names, file=sys.stderr)
            print('all_kwargs:', all_kwargs, file=sys.stderr)
            print('varnames:', attrs.varnames, file=sys.stderr)
            raise
        log('ar',
            lambda: f'updating arg slot at index {index} kw {kw} arg {arg}')
        arg_slots[index] = arg

    # Add defaults from any slots that still require them.
    for argno, note in enumerate(default_required):
        if note is None or arg_slots[argno] is not _Sentinel:
            continue
        assert isinstance(note, int), note
        arg_slots[argno] = defaults[note]

    for arg in arg_slots:
        if arg is _Sentinel:
            missing_count = sum(1 for arg in arg_slots if arg is _Sentinel)
            missing_names = [name for i, name in enumerate(arg_names)
                             if arg_slots[i] is _Sentinel]
            missing_str = _arg_join(missing_names)
            msg = '{}() missing {} required positional argument{}: {}'.format(
                    attrs.name, missing_count,
                    '' if missing_count == 1 else 's', missing_str)
            return Result(ExceptionData(
                traceback=None,
                parameter=None,
                exception=TypeError(msg)))

    # For convenience we inform the caller how many slots should be appended to
    # the arg_slots to reach the full number of local slots.
    remaining = attrs.nlocals - attrs.total_argcount
    assert remaining >= 0
    assert attrs.nlocals == len(attrs.varnames)

    log('ar', f'arg_slots: {len(arg_slots)} remaining: {remaining} '
              f'varnames ({len(attrs.varnames)}): {attrs.varnames} '
              f'cellvars: {attrs.cellvars} freevars: {attrs.freevars}')

    assert len(arg_slots) == attrs.total_argcount, \
        (len(arg_slots), attrs.total_argcount)
    assert len(arg_slots) + remaining == len(attrs.varnames), \
        (len(arg_slots), remaining, len(attrs.varnames))
    return Result((arg_slots, remaining))
