"""
REFERENCE TEMPLATE — Custom Python Detectors for TrustyAI Guardrails

This file is NOT deployed by default. The default deployment uses inline regex
patterns configured in values.yaml (guardrails.detectors.secretsRegex.patterns).

Use this file when you need detection logic beyond simple regex — for example:
  - Luhn validation for credit card numbers
  - Entropy checks for high-randomness strings
  - Context-aware detection (checking surrounding code structure)
  - External service calls (e.g. querying a secrets vault)

TO DEPLOY THIS FILE:
  1. Build a custom detector container image that includes this file at
     /app/custom_detectors/custom_detectors.py (use the base image from
     the TrustyAI operator: odh-built-in-detector-rhel9)
  2. Override the detector image in the GuardrailsOrchestrator CR

DETECTOR API:
  Each public function is auto-registered under the "custom" detector registry.
  - Input:  text (str) — the content to scan
  - Output: bool (True = flagged) or dict with start/end/text/detection/score
  - Prefix with _ to hide helper functions from the registry

HOW TO TEST (from inside the guardrails pod):
  curl -s http://localhost:8080/api/v1/text/contents \
    -H "Content-Type: application/json" \
    -d '{"contents": ["test AKIAIOSFODNN7EXAMPLE"],
         "detector_params": {"custom": {"aws_access_key": {}}}}'
"""

import re

# ── Helper (prefixed with _ so it's not exposed as a detector) ───────────


def _find_match(text, pattern, detection_type, detection_name):
    """Return a detection dict for the first regex match, or empty dict."""
    m = re.search(pattern, text)
    if not m:
        return {}
    return {
        "start": m.start(),
        "end": m.end(),
        "text": m.group(0),
        "detection_type": detection_type,
        "detection": detection_name,
        "score": 1.0,
    }


# ── Cloud Provider Keys ──────────────────────────────────────────────────


def aws_access_key(text: str) -> dict:
    """Detect AWS Access Key IDs (AKIA prefix + 16 uppercase alphanumeric)"""
    return _find_match(text, r"\bAKIA[0-9A-Z]{16}\b", "credential", "aws_access_key")


def aws_secret_key(text: str) -> dict:
    """Detect AWS Secret Access Keys (40 base64 chars near aws_secret)"""
    return _find_match(
        text,
        r'(?i)(?:aws_secret_access_key|aws_secret)\s*[:=]\s*["\x27]?([A-Za-z0-9/+=]{40})["\x27]?',
        "credential",
        "aws_secret_key",
    )


# ── Source Control Tokens ────────────────────────────────────────────────


def github_token(text: str) -> dict:
    """Detect GitHub personal access tokens (ghp_) and secret tokens (ghs_)"""
    return _find_match(
        text, r"\bgh[ps]_[A-Za-z0-9_]{36,}\b", "credential", "github_token"
    )


def gitlab_token(text: str) -> dict:
    """Detect GitLab personal/project/group access tokens"""
    return _find_match(
        text, r"\bglpat-[A-Za-z0-9\-_]{20,}\b", "credential", "gitlab_token"
    )


# ── AI/API Provider Keys ─────────────────────────────────────────────────


def openai_api_key(text: str) -> dict:
    """Detect OpenAI API keys (sk- prefix)"""
    return _find_match(text, r"\bsk-[A-Za-z0-9]{20,}\b", "credential", "openai_api_key")


def anthropic_api_key(text: str) -> dict:
    """Detect Anthropic API keys (sk-ant- prefix)"""
    return _find_match(
        text, r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b", "credential", "anthropic_api_key"
    )


# ── Messaging Tokens ─────────────────────────────────────────────────────


def slack_token(text: str) -> dict:
    """Detect Slack bot/user/app tokens (xoxb-, xoxp-, xoxa-, xoxr-, xoxs-)"""
    return _find_match(
        text, r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b", "credential", "slack_token"
    )


# ── Cryptographic Material ───────────────────────────────────────────────


def private_key(text: str) -> dict:
    """Detect PEM-encoded private key blocks (RSA, EC, DSA, OPENSSH, PGP)"""
    return _find_match(
        text,
        r"-----BEGIN\s+(?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
        "credential",
        "private_key",
    )


# ── Generic Patterns ─────────────────────────────────────────────────────


def generic_api_key_assignment(text: str) -> dict:
    """Detect api_key/api_secret/api_token assignments with long values"""
    return _find_match(
        text,
        r'(?i)\b(?:api[_-]?key|apikey|api[_-]?secret|api[_-]?token)\s*[:=]\s*["\x27]?[A-Za-z0-9_\-]{20,}["\x27]?',
        "credential",
        "generic_api_key",
    )


def bearer_token(text: str) -> dict:
    """Detect Bearer tokens in authorization headers"""
    return _find_match(
        text,
        r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*",
        "credential",
        "bearer_token",
    )
