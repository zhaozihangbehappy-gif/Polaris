from pathlib import Path
import tomllib


def load_service_config(path: str | Path = "app_config.toml") -> dict[str, object]:
    with Path(path).open("rb") as file:
        return tomllib.load(file)
