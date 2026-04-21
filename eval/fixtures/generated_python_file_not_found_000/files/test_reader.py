import os
import tempfile
import unittest

from reader import read_message


class ReadMessageTests(unittest.TestCase):
    def test_reads_message_when_called_from_another_directory(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as other_dir:
            os.chdir(other_dir)
            try:
                self.assertEqual(read_message(), "hello from the project")
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
