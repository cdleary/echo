import itertools

for i, item in enumerate(itertools.permutations('AB', 2)):
    if i == 0:
        assert item == ('A', 'B')
    else:
        assert i == 1
        assert item == ('B', 'A')
