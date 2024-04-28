import enum

class MyEnum(enum.Enum):
    MY = 'my'
    ENUMERATED = 'enumerated'
    ITEMS = 'items'


e = MyEnum.MY
assert e == MyEnum.MY
assert e == MyEnum('my')
assert e != MyEnum('enumerated')
assert isinstance(e, MyEnum), e

s = str(e)
assert s == 'MyEnum.MY', s
r = repr(e)
assert r == "<MyEnum.MY: 'my'>", r
print(e)
