import unittest

from greeter import greeting


class GreeterTest(unittest.TestCase):
    def test_greeting(self):
        self.assertEqual(greeting("Polaris"), "hello, Polaris")


if __name__ == "__main__":
    unittest.main()
