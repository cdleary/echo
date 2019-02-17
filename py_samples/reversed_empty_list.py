for e in reversed([]):
    assert False

for e in reversed([42]):
    assert e == 42

last = 0
for e in reversed([3, 2, 1]):
    assert e > last
    last = e
