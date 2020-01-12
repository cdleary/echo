from echo.common import camel_to_underscores


def camel_to_underscores_test():
    assert camel_to_underscores('FooBarBaz') == 'foo_bar_baz'
