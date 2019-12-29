path = []

def main():
    try:
        path.append(0)
        raise ValueError
    finally:
        path.append(1)
    path.append(-1)


try:
    main()
except ValueError:
    path.append(2)


assert path == [0, 1, 2]
