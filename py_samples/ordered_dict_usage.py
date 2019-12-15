from collections import OrderedDict


o = OrderedDict()
o['a'] = 42
o['b'] = 64
o['c'] = 77


assert o == dict(a=42, b=64, c=77)
