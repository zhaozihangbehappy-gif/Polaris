import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "src" / "native.c"


def main():
    compiler = os.environ.get("CC", "gcc")
    with tempfile.TemporaryDirectory() as build_dir:
        output = Path(build_dir) / "native.o"
        command = [compiler, "-c", str(SOURCE), "-o", str(output)]
        completed = subprocess.run(command)

    if completed.returncode:
        print(
            f"error: command '{compiler}' failed with exit code {completed.returncode}",
            file=sys.stderr,
        )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
