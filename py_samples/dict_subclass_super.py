class MyDict(dict):
    def do_set_item(self, k, v):
        super().__setitem__(k, v)


d = MyDict()
d.do_set_item('foo', 42)
assert d['foo'] == 42
