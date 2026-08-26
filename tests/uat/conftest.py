"""Pytest fixtures for PCA cluster UAT."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_E2E = Path(__file__).resolve().parent.parent / "e2e"
if str(_E2E) not in sys.path:
    sys.path.insert(0, str(_E2E))

from pca_e2e import oc


@pytest.fixture(scope="session")
def oc_user() -> str:
    try:
        return oc.whoami()
    except oc.OcError as exc:
        pytest.exit(f"oc whoami failed — log in to the cluster first: {exc}", returncode=1)


@pytest.fixture(scope="session")
def dev_namespace(oc_user: str) -> str:
    del oc_user
    value = os.environ.get("DEV_NAMESPACE", "").strip()
    if not value:
        pytest.skip("DEV_NAMESPACE not set — pass DEV_USER= to make uat")
    return value


@pytest.fixture(scope="session")
def require_dev_namespace(dev_namespace: str) -> str:
    return dev_namespace
