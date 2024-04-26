QUAD_SIZE = 8
DWORD_SIZE = 4
PYDICT_OFFSET_MA_USED = 2 * QUAD_SIZE  # ssize_t
PYDICT_OFFSET_MA_VERSION_TAG = 3 * QUAD_SIZE  # uint64_t
PYDICT_OFFSET_MA_KEYS = 4 * QUAD_SIZE  # PyDictKeysObject*
PYDICT_OFFSET_MA_VALUES = 5 * QUAD_SIZE  # PyObject**

PYDICTKEYS_OFFSET_DK_SIZE = 1 * QUAD_SIZE

PYVAR_OFFSET_OB_SIZE = 2 * QUAD_SIZE
PYVAR_OFFSET_OB_DIGIT = 3 * QUAD_SIZE
PYLONG_SHIFT = 30