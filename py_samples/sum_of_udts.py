class MyInt(int): pass


xs = [MyInt(1), MyInt(2), MyInt(3)]
s = sum(xs) 
assert s == 6, s
