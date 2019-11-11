class Derived(type):
    pass


assert super(Derived, Derived).__new__ is type.__new__
