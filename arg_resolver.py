import types
from typing import Text, Dict, Optional, Tuple, Any

from interp_result import Result


class CodeAttributes:
    STARARGS_FLAG = 0x04

    def __init__(self, argcount: int, kwonlyargcount: int, nlocals: int,
                 starargs: bool):
        self.argcount = argcount
        self.kwonlyargcount = kwonlyargcount
        self.nlocals = nlocals
        self.starargs = starargs

    def __repr__(self) -> Text:
        return ('CodeAttributes(argcount={}, kwonlyargcount={}, '
                'nlocals={}, starargs={})').format(
            self.argcount, self.kwonlyargcount, self.nlocals, self.starargs)

    @classmethod
    def from_code(cls, code: types.CodeType) -> 'CodeAttributes':
        return cls(argcount=code.co_argcount,
                   kwonlyargcount=code.co_kwonlyargcount,
                   nlocals=code.co_nlocals,
                   starargs=bool(code.co_flags & cls.STARARGS_FLAG))


def resolve_args(attrs: CodeAttributes,
                 args: Optional[Tuple[Any, ...]] = None,
                 kwargs: Optional[Dict[Text, Any]] = None,
                 defaults: Optional[Tuple[Any, ...]] = None) -> Result[
        Tuple[Tuple[Any, ...], int]]:
    """Returns the prefix that is added to local slots."""
    args = args or ()
    kwargs = kwargs or {}
    defaults = defaults or ()
    # Note: argcount includes default arguments in the count.
    assert (len(args) + len(defaults) >= attrs.argcount
            or attrs.starargs), (
        'Invocation did not provide enough arguments.', args, defaults,
        attrs)

    remaining = attrs.nlocals - attrs.argcount
    if kwargs:
        raise NotImplementedError(kwargs)
    return (args + defaults), remaining
