import unittest

from greeting import make_greeting


class GreetingTests(unittest.TestCase):
    def test_make_greeting(self):
        self.assertEqual(make_greeting("Ada"), "Hello, Ada!")


if __name__ == "__main__":
    unittest.main()
