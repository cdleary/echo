from collections import OrderedDict


o = OrderedDict()
o['a'] = 42
o['b'] = 64
o['c'] = 77


assert o == dict(a=42, b=64, c=77)


for i, k in enumerate(o):
    if i == 0:
        assert k == 'a'
    elif i == 1:
        assert k == 'b'
    else:
        assert i == 2
        assert k == 'c'
