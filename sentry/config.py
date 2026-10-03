"""Load config.toml (repo root by default). Laptop only: tomllib needs Python >= 3.11."""
import tomllib
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.toml"


def load(path=DEFAULT_PATH):
    with open(path, "rb") as f:
        return tomllib.load(f)
