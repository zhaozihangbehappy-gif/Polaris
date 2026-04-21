from pathlib import Path

value = Path("data/value.txt").read_text().strip()
print(value)
