#include <Python.h>

int answer_from_python_header(void) {
    return Py_IsInitialized() ? 42 : 7;
}
