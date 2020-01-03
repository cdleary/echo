class MyMeta(type): pass



assert MyMeta.__call__ is type.__call__
