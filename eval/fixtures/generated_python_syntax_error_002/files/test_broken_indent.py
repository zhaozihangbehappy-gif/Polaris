import unittest

from broken_indent import greeting


class GreetingTests(unittest.TestCase):
    def test_named_greeting(self):
        self.assertEqual(greeting("Ada"), "Hello, Ada!")


if __name__ == "__main__":
    unittest.main()
