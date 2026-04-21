from pathlib import Path


def write_status(message: str) -> Path:
    output = Path.cwd() / "status.txt"
    output.write_text(message + "\n", encoding="utf-8")
    return output
