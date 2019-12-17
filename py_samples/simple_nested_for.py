s = []

for x in 'ab':
    for y in 'cd':
        s.append((x, y))


assert s == [('a', 'c'), ('a', 'd'), ('b', 'c'), ('b', 'd')], s
