from io import StringIO
from contextlib import redirect_stdout

from echo.interp import run_function


def test_print_to_10():
    def main():
        for i in range(10):
            print(i)

    run_function(main)


def test_two_plus_three():
    def add(x, y): return x+y
    assert run_function(add, 2, 3) == 5


def test_call_other():
    def main():
        def sub(addend): return 42+addend
        return sub(0) + sub(1)
    assert run_function(main) == 85


def test_fizzbuzz():
    def fizzbuzz(x):
        for i in range(1, x):
            if i % 15 == 0:
                print('fizzbuzz', i)
            elif i % 3 == 0:
                print('fizz', i)
            elif i % 5 == 0:
                print('buzz', i)
    out = StringIO()
    with redirect_stdout(out):
        run_function(fizzbuzz, 16)
    assert out.getvalue() == """fizz 3
buzz 5
fizz 6
fizz 9
buzz 10
fizz 12
fizzbuzz 15
"""


def test_cond_with_bindings():
    def main():
        if True:
            x = 42
            y = 24
        else:
            x = 24
            y = 42
        return x, y
    assert run_function(main) == (42, 24)


def test_built_list_and_index():
    def main():
        lst = [1, 2, 3]
        return lst[1]
    assert run_function(main) == 2


def test_simple_cond_run_alternate():
    def main():
        if False:
            x = 42
        else:
            x = 24
        return x
    assert run_function(main) == 24


def test_kwarg_slot():
    def f(x, y=3):
        return x * y
    assert run_function(f, 1) == 3
    assert run_function(f, 1, 2) == 2


def test_mutating_closure_explicit_cell_object():
    def main():
        list_cell = [42]

        def inc(): list_cell[0] += 1
        inc()
        return list_cell[0]
    assert run_function(main) == 43


def test_mutating_closure_implicit_cell():
    def main():
        x = 0

        x += 1

        def inc():
            nonlocal x
            x += 1
        inc()
        x += 1
        return x
    assert run_function(main) == 3


def test_closed_over_argument():
    def main():
        def outer(x):
            def inner():
                return x
            x += 2
            return inner
        return outer(42)()

    assert run_function(main) == 44


def test_print_dict_keys():
    def main():
        x = dict(a=1, b=2)
        return str(sorted(list(x.keys())))

    assert run_function(main) == "['a', 'b']"


def test_tuple_unpack():
    def main():
        x = (1, 2, 3)
        y = (4, 5)
        z = (6,)
        return (*x, *y, *z)

    assert run_function(main) == tuple(range(1, 7))


def test_while_with_break_and_continue():
    def main():
        i = 0
        while True:
            if i >= 3:
                break
            if i < 1:
                i += 2
                continue
            i += 1
        return i

    assert run_function(main) == 3


# def test_stararg_invocation():
#     def main():
#         def add(x, y, z): return x+y+z
#         args = (2, 3)
#         return add(1, *args)
#
#     assert run_function(main) == 6
