from pathlib import Path


def load_city():
    return Path("city.txt").read_text(encoding="ascii").strip()
