import types

class MyContextManager:
    def __enter__(self): return 42
    def __exit__(self, exc_type, exc, exc_tb):
        assert exc_type is ValueError
        assert exc.args == ('whoo',)
        # TODO(cdleary): 2019-12-24 Need real traceback objects.
        #assert isinstance(exc_tb, types.TracebackType)
        return True  # Suppress!

with MyContextManager() as cm:
    assert cm == 42
    raise ValueError('whoo')
