class MyTypeError(TypeError):
    pass


assert issubclass(MyTypeError, Exception)
