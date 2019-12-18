for i in range(4):
    for j in range(2):
        if (i + j) % 3 == 0:
            break
    if i == j:
        break
else:
    assert False

assert i == 0, i
assert j == 0, j
