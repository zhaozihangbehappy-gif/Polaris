import os
import errno
import itertools


DEFAULT_PORT = int(os.environ.get("PORT", "46001"))
_RESERVED_PORTS = set()
_AUTO_PORTS = itertools.count(49152)


class DemoServer:
    def __init__(self, port):
        self._port = self._reserve(port)
        self.server_address = ("127.0.0.1", self._port)

    def _reserve(self, port):
        candidate = next(_AUTO_PORTS) if port == 0 else port
        if candidate in _RESERVED_PORTS:
            raise OSError(errno.EADDRINUSE, "Address already in use")
        _RESERVED_PORTS.add(candidate)
        return candidate

    def server_close(self):
        _RESERVED_PORTS.discard(self._port)


def make_server(port=None):
    if port is None:
        port = DEFAULT_PORT
    return DemoServer(port)
