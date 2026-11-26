from importlib import metadata

import tubes


def test_version_comes_from_pyproject_installed_or_not(monkeypatch):
    installed = tubes._version()

    def missing(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", missing)  # imported from src/ alone, as scripts/regroup.py does
    assert tubes._version() == installed == tubes.__version__
