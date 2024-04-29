import sys


def main():
    from types import GenericAlias

    assert GenericAlias(list, (int,)) == list[int]


# No GenericAlias in types until this point.
if sys.version_info[:2] > (3, 7):
    main()
