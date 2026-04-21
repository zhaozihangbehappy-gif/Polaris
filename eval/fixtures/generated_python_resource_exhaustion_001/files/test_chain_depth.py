import unittest

from chain_depth import leaf_depth, make_chain


class DeepChainTests(unittest.TestCase):
    def test_handles_generated_chain(self):
        chain = make_chain(1500)
        self.assertEqual(leaf_depth(chain), 1500)


if __name__ == "__main__":
    unittest.main()
