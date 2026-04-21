import sys
import tomllib
import unittest
from pathlib import Path


class PythonRequirementTest(unittest.TestCase):
    def test_declared_python_requirement_matches_runtime(self):
        data = tomllib.loads(Path("pyproject.toml").read_text())
        project = data["project"]
        required = project["requires-python"]
        minimum = tuple(map(int, required.removeprefix(">=").split(".")))
        current = sys.version_info[: len(minimum)]

        if current < minimum:
            version = ".".join(map(str, sys.version_info[:3]))
            self.fail(
                f"{project['name']} requires a different Python version: "
                f"{version} not in '{required}'"
            )


if __name__ == "__main__":
    unittest.main()
