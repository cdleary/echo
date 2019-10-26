from typing import Optional, Tuple, Text
import types


class CodeAttributes:
    STARARGS_FLAG = 0x04
    GENERATOR_FLAG = 0x20

    def __init__(self, argcount: int, kwonlyargcount: int, nlocals: int,
                 starargs: bool, varnames: Tuple[Text], generator: bool,
                 code: Optional[types.CodeType] = None):
        self.argcount = argcount
        self.kwonlyargcount = kwonlyargcount
        self.nlocals = nlocals
        self.varnames = varnames
        self.starargs = starargs
        self.generator = generator
        self.code = code

    @property
    def total_argcount(self) -> int:
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
        """Creates CodeAttributes with values extracted from VM code object."""
        return cls(argcount=code.co_argcount,
                   kwonlyargcount=code.co_kwonlyargcount,
                   nlocals=code.co_nlocals,
                   varnames=code.co_varnames,
                   starargs=bool(code.co_flags & cls.STARARGS_FLAG),
                   generator=bool(code.co_flags & cls.GENERATOR_FLAG),
                   code=code)
