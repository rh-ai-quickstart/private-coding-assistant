"""Helm-render checks that false booleans actually disable optional components."""

from __future__ import annotations

import subprocess

from helm_pca import AI_SERVING, REPO_ROOT, _docs, _helm_template

OPERATORS = REPO_ROOT / "charts" / "pca-operators"


def _operators(extra: list[str]) -> list[dict]:
    rendered = subprocess.run(
        ["helm", "template", "test", str(OPERATORS), *extra],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return _docs(rendered)


def _names(docs: list[dict], kind: str) -> list[str]:
    return [d["metadata"]["name"] for d in docs if d.get("kind") == kind]


def test_rhcl_disabled_drops_subscription_and_kuadrant():
    docs = _operators(["--set", "operators.rhcl.enabled=false"])
    assert "rhcl-operator" not in _names(docs, "Subscription")
    assert not [d for d in docs if d.get("kind") == "Kuadrant"]


def test_rhcl_enabled_by_default():
    docs = _operators([])
    assert "rhcl-operator" in _names(docs, "Subscription")
    assert [d for d in docs if d.get("kind") == "Kuadrant"]


def test_maas_disabled_drops_front_door_resources():
    docs = _docs(_helm_template(AI_SERVING, ["--set", "maas.enabled=false"]))
    kinds = {d.get("kind") for d in docs}
    assert "AuthPolicy" not in kinds
    assert "TokenRateLimitPolicy" not in kinds
    assert "maas-default-gateway" not in _names(docs, "HTTPRoute")


def test_maas_enabled_by_default():
    docs = _docs(_helm_template(AI_SERVING, []))
    assert "AuthPolicy" in {d.get("kind") for d in docs}
