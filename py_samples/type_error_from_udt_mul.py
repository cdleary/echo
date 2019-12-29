# Make a type that explodes when you try to multiply it.
class Exploder:
    def __mul__(self, other): raise TypeError('boom')

# Make a function that prints a simple math expression.
def f(a, b, c):
    print(a + b * c)

# Make a main routine that wraps up f so we can observe any error.
def main(a, b, c):
    try:
        f(a, b, c)
    except TypeError as e:
        pass
    else:
        raise AssertionError

# Invoke it all!
main(1, Exploder(), 3)
