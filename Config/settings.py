from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent


def load(file, section=None):
    """Reads one yaml file from Config/, or just one section of it

    Keyword arguments:
    file -- e.g. "model.yaml"
    section -- e.g. "allocator" (None = the whole file)
    """
    with open(CONFIG_DIR / file, encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    return settings if section is None else settings[section]


def sleeves():
    """The sleeve names from configs.yaml, plus the reserve --> ["vol", "equity", "spread", "reserve"]"""
    return list(load("configs.yaml", "sleeves")) + ["reserve"]
