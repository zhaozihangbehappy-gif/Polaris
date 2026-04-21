from setuptools import Extension, setup

setup(
    name="native-broken",
    version="0.1.0",
    packages=["native_broken"],
    ext_modules=[
        Extension("native_broken._speedups", ["native_broken/speedups.c"]),
    ],
)
