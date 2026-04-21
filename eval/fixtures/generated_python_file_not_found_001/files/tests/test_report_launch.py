import subprocess
import sys
import unittest
from pathlib import Path


class ReportLaunchTest(unittest.TestCase):
    def test_report_script_runs_from_project_root(self):
        project_root = Path(__file__).resolve().parents[1]
        tests_dir = project_root / "tests"

        result = subprocess.run(
            [sys.executable, "scripts/report.py"],
            cwd=tests_dir,
        )

        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
