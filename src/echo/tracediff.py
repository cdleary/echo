import itertools
import os
import pickle
import sys

import termcolor


def main():
    lhs_path, rhs_path = sys.argv[1:]

    with open(lhs_path, 'rb') as lhs_file:
        lhs_entries = pickle.load(lhs_file)
    with open(rhs_path, 'rb') as rhs_file:
        rhs_entries = pickle.load(rhs_file)

    print('lhs entries:', len(lhs_entries))
    print('rhs entries:', len(rhs_entries))

    diverged = False

    print('{:26} | {:26}'.format(os.path.basename(lhs_path),
                                 os.path.basename(rhs_path)))
    print('-' * 26, '|', '-' * 26)

    for lhs, rhs in zip(lhs_entries, rhs_entries):
        msg = '{:5d} {:20} | {:5d} {:20}'.format(
            lhs.instruction.offset, lhs.instruction.get_opname_str(),
            rhs.instruction.offset, rhs.instruction.get_opname_str())
        now_diverged = (
            lhs.instruction.offset != rhs.instruction.offset or
            (lhs.instruction.opname != 'LOAD_CONST' and
             lhs.instruction.argrepr != rhs.instruction.argrepr))
        if not diverged and now_diverged:
            termcolor.cprint(msg, color='red')
            diverged = True
        else:
            print(msg)

        if lhs.block_stack:
            print(lhs.get_block_stack_str())
        if rhs.block_stack:
            print(' ' * 28, rhs.get_block_stack_str())


if __name__ == '__main__':
    main()
