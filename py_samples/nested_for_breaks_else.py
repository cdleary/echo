s = []

for x in ('foo', 'bar'):
    for y in ('shooba', 'dooba'):
        if x == y:
            s.append('x == y')
            break
        if x != y:
            s.append('x != y')
            break
else:
    s.append('else')


assert s == ['x != y', 'x != y', 'else'], s
