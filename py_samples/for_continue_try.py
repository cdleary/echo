accum = 0
for i in range(4):
    try:
        if i % 2 == 0:
            continue
    finally:
        accum += i

assert accum == 0+1+2+3, accum
