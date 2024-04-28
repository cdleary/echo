from typing import Any, Callable, Optional

from echo.interpreter_state import InterpreterState
from echo.interp_result import ExceptionData


EModule = Any


class ICtx:
    """Interpreter context."""
    desc_count: int  # Hack, number of descriptor uses we've done.

    def __init__(self, interp_state: InterpreterState,
                 interp_callback: Callable, do_call_callback: Callable,
                 ebuiltins: EModule, esys: EModule):
        self.interp_state = interp_state
        self.interp_callback = interp_callback
        self.do_call_callback = do_call_callback
        interp_state.sys_modules['builtins'] = ebuiltins
        interp_state.sys_modules['sys'] = esys
        self.ebuiltins = ebuiltins
        self.desc_count = 0
        self.exc_info: Optional[ExceptionData] = None
        self.call_profiler = None

    def call(self, *args, **kwargs):
        return self.do_call_callback(*args, **kwargs, ictx=self)

    def get_ebuiltins(self):
        return self.ebuiltins
