import subprocess
import sys
import unittest
from pathlib import Path


class ReportRunnerTest(unittest.TestCase):
    def test_runner_emits_unicode_report(self):
        runner = Path(__file__).with_name("report_runner.py")
        result = subprocess.run(
            [sys.executable, str(runner)],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("café", result.stdout)


if __name__ == "__main__":
    unittest.main()
