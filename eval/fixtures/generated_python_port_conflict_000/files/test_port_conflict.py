import unittest

from server import make_server


class PortConfigurationTest(unittest.TestCase):
    def test_parallel_instances_can_start(self):
        first = make_server()
        self.addCleanup(first.server_close)

        second = make_server()
        self.addCleanup(second.server_close)

        self.assertNotEqual(first.server_address, second.server_address)


if __name__ == "__main__":
    unittest.main()
