from typing import Any, Callable

from echo.interp_result import Result
from echo.eobjects import get_guest_builtin
from echo.interp_context import ICtx


def foreach(iterable: Any, callback: Callable[[Any], Result[bool]],
            ictx: ICtx) -> Result[None]:
    do_iter = get_guest_builtin('iter')
    do_next = get_guest_builtin('next')
    it = do_iter.invoke((iterable,), {}, {}, ictx)
    if it.is_exception():
        return Result(it.get_exception())
    it = it.get_value()
    while True:
        item = do_next.invoke((it,), {}, {}, ictx)
        if (item.is_exception() and isinstance(
                item.get_exception().exception, StopIteration)):
            break
        if item.is_exception():
            return Result(item.get_exception())

        cb_res = callback(item.get_value())
        if cb_res.is_exception():
            return Result(cb_res.get_exception())
        keep_going = cb_res.get_value()
        assert isinstance(keep_going, bool), keep_going
        if not keep_going:
            break

    return Result(None)
