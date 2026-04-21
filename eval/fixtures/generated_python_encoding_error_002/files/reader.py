from pathlib import Path


def load_greeting():
    return Path(__file__).with_name("greeting.txt").read_text()
