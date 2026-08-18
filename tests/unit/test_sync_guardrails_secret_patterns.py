"""Unit tests for guardrails secret pattern sync from gitleaks."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sync-guardrails-secret-patterns.py"
VENDOR_TOML = REPO_ROOT / "scripts" / "vendor" / "gitleaks-v8.24.2.toml"
OVERRIDES_PATH = (
    REPO_ROOT
    / "charts"
    / "pca-ai-serving"
    / "charts"
    / "pca-guardrails"
    / "files"
    / "secret-patterns-overrides.yaml"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "charts"
    / "pca-ai-serving"
    / "charts"
    / "pca-guardrails"
    / "files"
    / "secret-patterns.yaml"
)
CHART_PATH = REPO_ROOT / "charts" / "pca-ai-serving" / "charts" / "pca-guardrails"


@pytest.fixture(scope="module")
def sync_mod():
    spec = importlib.util.spec_from_file_location("sync_guardrails_secret_patterns", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_guardrails_secret_patterns"] = module
    spec.loader.exec_module(module)
    return module


def test_vendor_toml_exists():
    assert VENDOR_TOML.is_file()


def test_extract_gitleaks_regexes_returns_many_patterns(sync_mod):
    patterns, skipped = sync_mod.extract_gitleaks_regexes(VENDOR_TOML)
    assert len(patterns) >= 150
    assert len(skipped) > 0


def test_committed_secret_patterns_is_fresh(sync_mod):
    patterns, _ = sync_mod.build_pattern_list()
    metadata = {
        "gitleaks_version": sync_mod.GITLEAKS_VERSION,
        "vendor_file": "scripts/vendor/gitleaks-v8.24.2.toml",
        "synced_at": sync_mod.date.today().isoformat(),
        "pattern_count": len(patterns),
    }
    expected = sync_mod._format_yaml(metadata, patterns)
    assert OUTPUT_PATH.is_file()
    current = OUTPUT_PATH.read_text(encoding="utf-8")
    # Ignore synced_at line drift by comparing pattern entry counts.
    assert current.count("\n  - ") == expected.count("\n  - ")


def test_stripe_live_pattern_in_generated_file():
    text = OUTPUT_PATH.read_text(encoding="utf-8")
    assert "sk|rk" in text and "live" in text


def test_generic_api_key_rule_excluded(sync_mod):
    """generic-api-key is too broad for block-mode IDE chat (false positives)."""
    patterns, _ = sync_mod.build_pattern_list()
    broad = [
        p
        for p in patterns
        if "passw(?:or)?d" in p and "access|auth" in p and "credential" in p
    ]
    assert not broad, "generic-api-key pattern should be removed via remove_ids"


def test_helm_detectors_json_includes_pii_and_secrets():
    result = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(CHART_PATH),
            "--set",
            "guardrails.proxy.enabled=true",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "name: DETECTORS_JSON" in result.stdout
    assert "name: LANGFUSE_PUBLIC_KEY" in result.stdout
    assert "kind: ServiceMonitor" in result.stdout
    assert "path: /metrics" in result.stdout
    svc_docs = [
        d
        for d in result.stdout.split("---")
        if re.search(r"(?m)^kind:\s*Service\s*$", d)
    ]
    assert svc_docs, "expected guardrails-proxy Service"
    assert "matchLabels:" not in svc_docs[0]
    for marker in ("email", "us-social-security-number", "us-phone-number", "ipv4"):
        assert marker in result.stdout
    assert "AKIA" in result.stdout or "akia" in result.stdout.lower()


def test_sync_check_mode_passes():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
