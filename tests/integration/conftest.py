"""Integration-suite fixtures: the CLI (in-process and as a real process, strata_python.testing's runners) and the HTTP API over real on-disk files."""

import os

import pytest
from fastapi.testclient import TestClient
from strata_python.testing import run_cli, run_module

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))


@pytest.fixture
def cli():
    """`cli('channels', '--json')` -> CliResult(stdout, stderr, code), in this process. Raises AssertionError with the output on a non-zero exit unless `check=False`."""
    from tubes import cli as C

    return lambda *args, check=True: run_cli(C.main, *args, check=check)


@pytest.fixture
def cli_subprocess(isolated_env):
    """The same through a real `python -m tubes` process: for the entry-point smoke test and anything that must not share this process's state."""
    return lambda *args, check=True: run_module("tubes", *args, src=SRC, check=check)


@pytest.fixture
def client():
    """The HTTP API over the real on-disk data and settings files."""
    from tubes.server.app import create_app

    return TestClient(create_app())
