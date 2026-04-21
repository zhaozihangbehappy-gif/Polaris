import subprocess
import sys


def run_worker():
    subprocess.run(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        check=True,
        timeout=1,
    )


if __name__ == "__main__":
    run_worker()
