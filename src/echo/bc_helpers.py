from typing import Callable, Tuple


def do_CALL_FUNCTION(fpop_n: Callable[[int], Tuple], arg: int, version_info):
    # https://docs.python.org/3.7/library/dis.html#opcode-CALL_FUNCTION
    #
    # Note: As of Python 3.6 this only supports calls for functions with
    # positional arguments.
    if version_info >= (3, 6):
        argc = arg
        kwargc = 0
    else:
        argc = arg & 0xff
        kwargc = arg >> 8
    kwarg_stack = fpop_n(2 * kwargc)
    kwargs = dict(zip(kwarg_stack[::2], kwarg_stack[1::2]))
    args = fpop_n(argc)
    f = fpop_n(1)[0]
    return (f, args, kwargs)
