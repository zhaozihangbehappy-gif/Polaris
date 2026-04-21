import unittest

from app import greet


class GreetingTests(unittest.TestCase):
    def test_greet_formats_name(self):
        self.assertEqual(greet("Ada"), "Hello, Ada!")


if __name__ == "__main__":
    unittest.main()
