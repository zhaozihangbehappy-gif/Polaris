from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
BUILD.mkdir(exist_ok=True)

subprocess.check_call(
    [
        "cc",
        "-c",
        str(ROOT / "native_module.c"),
        "-o",
        str(BUILD / "native_module.o"),
    ]
)
