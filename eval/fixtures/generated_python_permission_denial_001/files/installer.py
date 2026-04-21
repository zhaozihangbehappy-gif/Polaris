import os
import pathlib
import shutil


def _enabled(value):
    return value.lower() in {"1", "true", "yes"}


def install_marker():
    if _enabled(os.environ.get("PIP_USER", "")):
        target = pathlib.Path(".user-site-packages")
        target.mkdir(exist_ok=True)
        marker = target / "pip-marker.txt"
        marker.write_text("installed with --user\n", encoding="utf-8")
        return marker

    target = pathlib.Path(".system-site-packages")
    if target.exists():
        target.chmod(0o755)
        shutil.rmtree(target)
    target.mkdir()
    target.chmod(0o555)
    marker = target / "pip-marker.txt"
    marker.write_text("installed without --user\n", encoding="utf-8")
    return marker
