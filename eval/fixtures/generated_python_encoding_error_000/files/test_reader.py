import unittest

from reader import load_city


class ReaderTest(unittest.TestCase):
    def test_city_name_is_read(self):
        self.assertEqual(load_city(), "München")


if __name__ == "__main__":
    unittest.main()
