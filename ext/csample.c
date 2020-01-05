#include <Python.h>

typedef struct {
    PyObject_HEAD
    /* Type-specific fields go here. */
} CSampleObject;

static PyTypeObject CSampleType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "csample.CSample",
    .tp_doc = "CSample objects",
    .tp_basicsize = sizeof(CSampleObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
};

static PyModuleDef csamplemodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "csample",
    .m_doc = "Example module that creates an extension type.",
    .m_size = -1,
};

PyMODINIT_FUNC PyInit_csample(void) {
    PyObject *m;
    if (PyType_Ready(&CSampleType) < 0)
        return NULL;

    m = PyModule_Create(&csamplemodule);
    if (m == NULL)
        return NULL;

    Py_INCREF(&CSampleType);
    if (PyModule_AddObject(m, "CSample", (PyObject *) &CSampleType) < 0) {
        Py_DECREF(&CSampleType);
        Py_DECREF(m);
        return NULL;
    }

    return m;
}
