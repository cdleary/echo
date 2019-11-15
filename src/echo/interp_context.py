from echo.interpreter_state import InterpreterState


class ICtx:
    """Interpreter context."""
    desc_count: int  # Hack, number of descriptor uses we've done.

    def __init__(self, interp_state: InterpreterState, interp_callback,
                 do_call_callback):
        self.interp_state = interp_state
        self.interp_callback = interp_callback
        self.do_call_callback = do_call_callback
        self.desc_count = 0

    def call(self, *args, **kwargs):
        return self.do_call_callback(*args, **kwargs, ictx=self)
