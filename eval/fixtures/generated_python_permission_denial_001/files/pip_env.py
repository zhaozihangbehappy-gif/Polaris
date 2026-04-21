import os


def configure_install_environment():
    os.environ.pop("PIP_USER", None)
