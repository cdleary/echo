from io import StringIO
from contextlib import redirect_stdout

from interp import interp
from common import get_code


def test_print_to_10():
    def main():
        for i in range(10):
            print(i)

    interp(get_code(main), globals())


def test_two_plus_two():
    add = lambda x, y: x+y
    assert interp(get_code(add), globals(), args=(2, 3)) == 5


def test_call_other():
    def main():
        sub = lambda addend: 42+addend
        return sub(0) + sub(1)
    assert interp(get_code(main), globals()) == 85


def test_fizzbuzz():
    def fizzbuzz(x):
        for i in range(1,x):
            if i % 15 == 0:
                print('fizzbuzz', i)
            elif i % 3 == 0:
                print('fizz', i)
            elif i % 5 == 0:
                print('buzz', i)
    out = StringIO()
    with redirect_stdout(out):
        interp(get_code(fizzbuzz), globals(), args=(16,))
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
    assert interp(get_code(main), globals()) == (42, 24)


def test_simple_cond_run_alternate():
    def main():
        if False: x = 42
        else: x = 24
        return x
    assert interp(get_code(main), globals()) == 24
