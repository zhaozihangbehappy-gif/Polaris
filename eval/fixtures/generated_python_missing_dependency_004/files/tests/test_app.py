import unittest

from app.__init__.helpers import label


class AppImportTest(unittest.TestCase):
    def test_label(self):
        self.assertEqual(label(), "ready")


if __name__ == "__main__":
    unittest.main()
