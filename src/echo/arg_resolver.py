"""Helpers for resolving given args/kwargs to frame slots."""

import pprint
import sys
import types
from typing import Text, Dict, Optional, Tuple, Any, List, Sequence

from echo.interp_result import Result, ExceptionData
from echo import code_attributes

from termcolor import cprint


def _arg_join(arg_names: Sequence[Text]) -> Text:
    if len(arg_names) == 1:
        return "'{}'".format(arg_names[0])
    pieces = []
    for name in arg_names:
        pieces.append("'{}'".format(name))
    s = ', '.join(pieces[:-1])
    return s + ', and ' + pieces[-1]


def resolve_args(attrs: code_attributes.CodeAttributes,
                 args: Optional[Tuple[Any, ...]] = None,
                 kwargs: Optional[Dict[Text, Any]] = None,
                 defaults: Optional[Tuple[Any, ...]] = None,
                 kwarg_defaults: Optional[Dict[Text, Any]] = None) -> Result[
        Tuple[List[Any], int]]:
    """Returns argument prefix that is pre-pended to local slots of a frame."""
    args = args or ()
    kwargs = kwargs or {}
    defaults = defaults or ()
    kwarg_defaults = kwarg_defaults or {}

    class Sentinel:
        """Used to ensure we fill in all argument slots."""

    # The functionality of this method is to populate these arg slots
    # appropriately.
    arg_slots = [Sentinel] * (attrs.total_argcount + attrs.starkwargs)

    if attrs.starargs:
        # Note: somewhat surprisingly, the arg slot for the varargs doesn't
        # live at its corresponding position in the argument list; instead,
        # Python appears to put it as the last argument, always.
        stararg_index = attrs.total_argcount-1
        arg_slots[stararg_index] = ()
    else:
        stararg_index = None
        if len(args) > attrs.total_argcount:
            msg = '{}() takes {} positional arguments but {} {} given'.format(
                    attrs.name, attrs.total_argcount, len(args),
                    'was' if len(args) == 1 else 'were')
            return Result(ExceptionData(
                traceback=None,
                parameter=msg,
                exception=TypeError(msg)))

    if attrs.starkwargs:
        starkwarg_index = attrs.total_argcount
        arg_slots[starkwarg_index] = {}
    else:
        starkwarg_index = None

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
    default_required = [None] * attrs.total_argcount
    if defaults:
        default_required[-len(defaults):] = list(range(len(defaults)))

    def in_stararg_position(argno: int) -> Tuple[bool, int]:
        if attrs.starargs:
            needed_at_end = attrs.kwonlyargcount
            needed_at_start = attrs.argcount
            if argno < needed_at_start:
                return (False, argno)
            if argno >= len(args)-needed_at_end:
                delta_from_end = len(args)-argno
                return (False, len(arg_slots)-delta_from_end-1)
            assert stararg_index is not None
            return (True, stararg_index)
        return (False, argno)

    def populate_positional(argno: int, value: Any) -> None:
        assert len(default_required) == attrs.total_argcount, default_required
        stararg_info = in_stararg_position(argno)
        argno = stararg_info[1]  # Stararg can update the slot index.
        if stararg_info[0]:
            arg_slots[stararg_index] = arg_slots[stararg_index] + (value,)
        else:
            assert argno < len(arg_slots), (
                'Argument number is out of range of argument slots.', argno,
                attrs, getattr(attrs, 'code', None), value)
            arg_slots[argno] = value
            default_required[argno] = None

    # Populate the positional arguments.
    for argno, arg in enumerate(args):
        populate_positional(argno, arg)

    # Populate the keyword arguments.
    all_kwargs = dict(kwarg_defaults)
    all_kwargs.update(kwargs)
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
        populate_positional(index, arg)

    # Add defaults from any slots that still require them.
    for argno, note in enumerate(default_required):
        if note is None:
            continue
        assert isinstance(note, int), note
        arg_slots[argno] = defaults[note]

    for arg in arg_slots:
        if arg == Sentinel:
            missing_count = sum(1 for arg in arg_slots if arg == Sentinel)
            missing_names = [name for i, name in enumerate(arg_names)
                             if arg_slots[i] == Sentinel]
            missing = _arg_join(missing_names)
            msg = '{}() missing {} required positional argument{}: {}'.format(
                    attrs.name, missing_count,
                    '' if missing_count == 1 else 's', missing)
            return Result(ExceptionData(
                traceback=None,
                parameter=msg,
                exception=TypeError(msg)))

    # For convenience we inform the caller how many slots should be appended to
    # reach the number of local slots.
    remaining = attrs.nlocals - attrs.total_argcount
    return Result((arg_slots, remaining))
