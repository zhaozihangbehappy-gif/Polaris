#include <Python.h>
#include <definitely_missing_system_header.h>

static PyObject *fast_add(PyObject *self, PyObject *args) {
    long a;
    long b;
    if (!PyArg_ParseTuple(args, "ll", &a, &b)) {
        return NULL;
    }
    return PyLong_FromLong(a + b);
}

static PyMethodDef methods[] = {
    {"fast_add", fast_add, METH_VARARGS, "Add two integers."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_speedups",
    NULL,
    -1,
    methods,
};

PyMODINIT_FUNC PyInit__speedups(void) {
    return PyModule_Create(&module);
}
