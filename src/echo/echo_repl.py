import optparse
import os
import readline
import sys
import types
import typing


try:
    import echo
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(
        os.path.realpath(__file__))))


from echo import interp


def main():
    parser = optparse.OptionParser(__doc__)
    opts, args = parser.parse_args()
    if len(args) != 0:
        parser.error('A single file argument is required')
    globals_ = dict(globals())
    state = interp.InterpreterState(os.getcwd())
    state.paths = sys.path[1:] + state.paths

    while True:
        line = input('>>> ')
        code = compile(line, '<stdin>', 'single')
        code = typing.cast(types.CodeType, code)
        result = interp.interp(code, globals_=globals_, state=state,
                               in_function=False)
        if result.is_exception():
            print('exception!', result.get_exception())


if __name__ == '__main__':
    main()
