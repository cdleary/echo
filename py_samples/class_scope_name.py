class Foo:
    class_scope_name = __name__

    def __init__(self):
        self.instance_method_scope_name = __name__


f = Foo()
assert f.class_scope_name == '__main__'
assert f.instance_method_scope_name == '__main__'
