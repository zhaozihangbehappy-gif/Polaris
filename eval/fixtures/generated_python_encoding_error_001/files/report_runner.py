import os
import subprocess
import sys
from pathlib import Path


def main():
    env = os.environ.copy()
    env.update(
        {
            "LC_ALL": "C",
            "LANG": "C",
            "PYTHONUTF8": "0",
            "PYTHONCOERCECLOCALE": "0",
        }
    )
    env.pop("PYTHONIOENCODING", None)

    worker = Path(__file__).with_name("report_worker.py")
    return subprocess.call([sys.executable, str(worker)], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
