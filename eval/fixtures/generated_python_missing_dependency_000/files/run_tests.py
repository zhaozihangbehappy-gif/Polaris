import subprocess
import sys


result = subprocess.run([sys.executable, "tests/test_greeter.py"])
raise SystemExit(result.returncode)
