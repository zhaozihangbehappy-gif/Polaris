import os
import stat
import tempfile
import unittest
from pathlib import Path

from writer import write_status


class WriterTests(unittest.TestCase):
    def test_status_can_be_written_from_read_only_cwd(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            sealed = Path(tmp) / "sealed"
            sealed.mkdir()
            sealed.chmod(stat.S_IREAD | stat.S_IEXEC)
            try:
                os.chdir(sealed)
                write_status("ready")
            finally:
                os.chdir(original_cwd)
                sealed.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
