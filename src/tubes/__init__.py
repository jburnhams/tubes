"""tubes: a curated, self-hosted video library that fetches on demand and plays while it downloads."""

from importlib.metadata import version

__version__ = version("tubes")  # pyproject.toml is the one place the version is written
# What Tubes says it is to the services it asks (strata-python's Http requires one): the app and what it is for, never a person.
USER_AGENT = f"tubes/{__version__} (home video library)"
