from echo import compiler

import unittest


@unittest.skip('code generator not yet fully implemented')
def test_proc7():
    def Proc7(IntParI1: int, IntParI2: int) -> int:
        IntLoc = IntParI1 + 2
        IntParOut = IntParI2 + IntLoc
        return IntParOut

    compiler.compile(Proc7.__code__, arg_types=(int, int))
