import types
from typing import Text, Dict, Optional, Tuple, Any, List

from interp_result import Result


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

    def __repr__(self) -> Text:
        return ('CodeAttributes(argcount={0.argcount}, '
                'kwonlyargcount={0.kwonlyargcount}, '
                'nlocals={0.nlocals}, varnames={0.varnames}, '
                'starargs={0.starargs})').format(self)

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

    # Note: argcount includes default arguments in the count.
    assert (len(args) + len(defaults) >= attrs.argcount
            or attrs.starargs), (
        'Invocation did not provide enough arguments.', args, defaults,
        attrs)

    if kwargs:
        raise NotImplementedError(attrs)
    if kwarg_defaults:
        raise NotImplementedError(attrs)

    if len(args) < attrs.argcount:
        # If we were presented with fewer arguments than the argcount for the
        # function, we fill in those values with defaults.
        defaults_required = attrs.argcount-len(args)
        result = args + defaults[-defaults_required:]
    else:
        result = args

    # We should always end up with a number of slots equivalent to "argcount",
    # which is a prefix on the "nlocals" slots.
    assert len(result) == attrs.argcount, (len(result), attrs, len(args),
                                           defaults)

    # For convenience we inform the caller how many slots should be appended to
    # reach the number of local slots.
    remaining = attrs.nlocals - attrs.argcount
    return list(result), remaining
