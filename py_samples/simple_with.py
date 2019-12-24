did_exit = False

class MyContextManager:
    def __enter__(self): return 42
    def __exit__(self, exc_type, exc, exc_tb):
        global did_exit
        assert exc_type is None
        assert exc is None
        assert exc_tb is None
        did_exit = True

with MyContextManager() as cm:
    assert cm == 42

assert did_exit
