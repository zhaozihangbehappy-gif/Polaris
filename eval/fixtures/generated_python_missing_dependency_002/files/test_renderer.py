import unittest

from renderer import normalized_label


class RendererTest(unittest.TestCase):
    def test_normalized_label(self):
        self.assertEqual(normalized_label("id=7;name=alpha"), "ALPHA")


if __name__ == "__main__":
    unittest.main()
