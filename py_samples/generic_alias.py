from types import GenericAlias

GenericAlias(list, (int,)) == list[int]
