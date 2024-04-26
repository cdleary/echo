def cell_factory():
    a = 1
    def f():
        nonlocal a
    return f.__closure__[0]

cell = cell_factory()
print('cell:', cell)
CellType = type(cell)
print('CellType:', CellType)
print('CellType name:', CellType.__name__)
assert CellType.__name__ == 'cell'
