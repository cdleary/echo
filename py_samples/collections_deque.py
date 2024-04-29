from collections import deque


def main():
    d = deque()
    d.append(42)
    d.appendleft(17)
    assert d.popleft() == 17
    assert d.popleft() == 42
    assert not d



main()
