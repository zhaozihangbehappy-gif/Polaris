from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
EMPTY_INDEX = (ROOT / "empty-index").as_uri()

cmd = [
    sys.executable,
    "-m",
    "pip",
    "install",
    "--dry-run",
    "--break-system-packages",
    "--disable-pip-version-check",
    "--no-cache-dir",
    "--index-url",
    EMPTY_INDEX,
    "-r",
    str(ROOT / "requirements.txt"),
]

raise SystemExit(subprocess.run(cmd).returncode)
