"""tubes: a curated, self-hosted video library that fetches on demand and plays while it downloads."""

import importlib.metadata as _metadata  # not `metadata`: tubes.metadata is a module of its own
import tomllib
from pathlib import Path


def _version() -> str:
    """pyproject.toml is the one place the version is written: read back from the installed metadata, or from the file itself when the
    package is imported from src/ without being installed (scripts/regroup.py's own `uv run --script` environment)."""
    try:
        return _metadata.version("tubes")
    except _metadata.PackageNotFoundError:
        with (Path(__file__).parents[2] / "pyproject.toml").open("rb") as f:
            return str(tomllib.load(f)["project"]["version"])


__version__ = _version()
# What Tubes says it is to the services it asks (strata-python's Http requires one): the app and what it is for, never a person.
USER_AGENT = f"tubes/{__version__} (home video library)"
