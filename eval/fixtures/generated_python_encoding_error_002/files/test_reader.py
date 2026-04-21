import unittest

from reader import load_greeting


class ReaderTest(unittest.TestCase):
    def test_loads_greeting(self):
        self.assertEqual(load_greeting(), "café\n")


if __name__ == "__main__":
    unittest.main()
