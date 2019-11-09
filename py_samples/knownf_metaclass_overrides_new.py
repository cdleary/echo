class MyMeta(type):
    def __new__(mcls, name, bases, namespace, **kwargs):
        print('mcls: {} name: {} bases: {} ns: {} kwargs: {}'.format(
            mcls, name, bases, namespace, kwargs))
        s = super(MyMeta, mcls)
        print('super:', s)
        cls = s.__new__(mcls, name, bases, namespace)
        print('cls:', cls)
        return cls


class Foo(metaclass=MyMeta):
    pass
