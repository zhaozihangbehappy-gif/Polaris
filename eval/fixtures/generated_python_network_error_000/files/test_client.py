import unittest
from unittest import mock

from client import fetch_banner


class ReadySocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def recv(self, size):
        return b"ready"


class StartingService:
    def __init__(self):
        self.attempts = 0

    def connect(self, address, timeout):
        self.attempts += 1
        if self.attempts < 3:
            raise ConnectionRefusedError(111, "Connection refused")
        return ReadySocket()


class ClientTest(unittest.TestCase):
    def test_client_waits_for_service_startup(self):
        service = StartingService()

        with mock.patch("socket.create_connection", side_effect=service.connect):
            self.assertEqual(fetch_banner("127.0.0.1", 8080), "ready")
