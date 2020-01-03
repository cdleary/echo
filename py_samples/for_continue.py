accum = 0
for i in range(4):
    if i % 2 == 0:
        continue
    accum += i

assert accum == 4, accum
