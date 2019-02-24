import sys
import types
from typing import Text, Dict, Optional, Tuple, Any, List

from interp_result import Result

from termcolor import cprint


class CodeAttributes:
    STARARGS_FLAG = 0x04

    def __init__(self, argcount: int, kwonlyargcount: int, nlocals: int,
                 starargs: bool, varnames: Tuple[Text],
                 code: Optional[types.CodeType] = None):
        self.argcount = argcount
        self.kwonlyargcount = kwonlyargcount
        self.nlocals = nlocals
        self.varnames = varnames
        self.starargs = starargs
        self.code = code

    @property
    def total_argcount(self):
        """Returns the total number of argument slots.

        In functions like:

            def f(x, *, y=3, z=4): ...

        argcount=1 and kwargcount=2, but there are three local slots
        attributable to args. This attribute is `3` for that function.
        """
        return self.argcount + self.kwonlyargcount + self.starargs

    def __repr__(self) -> Text:
        return ('CodeAttributes(argcount={0.argcount}, '
                'kwonlyargcount={0.kwonlyargcount}, '
                'nlocals={0.nlocals}, varnames={0.varnames}, '
                'starargs={0.starargs}, '
                'total_argcount={0.total_argcount})').format(self)

    @classmethod
    def from_code(cls, code: types.CodeType) -> 'CodeAttributes':
        return cls(argcount=code.co_argcount,
                   kwonlyargcount=code.co_kwonlyargcount,
                   nlocals=code.co_nlocals,
                   varnames=code.co_varnames,
                   starargs=bool(code.co_flags & cls.STARARGS_FLAG),
                   code=code)


def resolve_args(attrs: CodeAttributes,
                 args: Optional[Tuple[Any, ...]] = None,
                 kwargs: Optional[Dict[Text, Any]] = None,
                 defaults: Optional[Tuple[Any, ...]] = None,
                 kwarg_defaults: Optional[Dict[Text, Any]] = None) -> Result[
        Tuple[List[Any], int]]:
    """Returns the argument prefix that is pre-pended to local slots."""
    args = args or ()
    kwargs = kwargs or {}
    defaults = defaults or ()
    kwarg_defaults = kwarg_defaults or {}

    class Sentinel:
        """Used to ensure we fill in all argument slots."""

    # The functionality of this method is to populate these arg slots
    # appropriately.
    arg_slots = [Sentinel] * attrs.total_argcount

    if attrs.starargs:
        # Note: somewhat surprisingly, the arg slot for the varargs doesn't
        # live at its corresponding position in the argument list; instead,
        # Python appears to put it as the last argument, always.
        stararg_index = attrs.total_argcount-1
        arg_slots[stararg_index] = ()
    else:
        stararg_index = None

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

    def in_stararg_position(argno):
        if attrs.starargs:
            needed_at_end = attrs.kwonlyargcount
            needed_at_start = attrs.argcount
            if argno < needed_at_start:
                return (False, argno)
            if argno >= len(args)-needed_at_end:
                delta_from_end = len(args)-argno
                return (False, len(arg_slots)-delta_from_end-1)
            return (True, stararg_index)
        return (False, argno)

    def populate_positional(argno: int, value: Any):
        assert len(arg_slots) == attrs.total_argcount
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
            print('keyword:  ', kw, file=sys.stderr)
            print('arg_names:', arg_names, file=sys.stderr)
            raise
        populate_positional(index, arg)

    # Add defaults from any slots that still require them.
    for argno, note in enumerate(default_required):
        if note is None:
            continue
        assert isinstance(note, int), note
        arg_slots[argno] = defaults[note]

    for arg in arg_slots:
        assert arg != Sentinel, arg_slots

    # For convenience we inform the caller how many slots should be appended to
    # reach the number of local slots.
    remaining = attrs.nlocals - attrs.total_argcount
    return Result((arg_slots, remaining))
