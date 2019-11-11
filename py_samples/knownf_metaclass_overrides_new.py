new_count = 0

class MyMeta(type):
    def __new__(mcls, name, bases, namespace, **kwargs):
        # Prevent accidental recursion.
        global new_count
        new_count += 1
        assert new_count <= 1

        print('mcls: {} name: {} bases: {} ns: {} kwargs: {}'.format(
            mcls, name, bases, namespace, kwargs))
        s = super(MyMeta, mcls)
        print('super:', s)
        super_new = s.__new__
        print('super.__new__:', super_new)
        #assert super_new is type.__new__
        cls = super_new(mcls, name, bases, namespace)
        print('cls:', cls)
        return cls


class Foo(metaclass=MyMeta):
    pass
