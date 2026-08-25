"""Lock copies that Helm charts cannot share across chart boundaries."""

from __future__ import annotations

from pathlib import Path

CHARTS = Path(__file__).resolve().parents[2] / "charts"
AI = CHARTS / "pca-ai-serving"
PLATFORM = CHARTS / "pca-platform-config"
GUARDRAILS_SSE = AI / "charts" / "pca-guardrails" / "files" / "sse_http.py"
ROUTER_SSE = AI / "charts" / "pca-semantic-router" / "files" / "sse_http.py"


def _define_body(path: Path, name: str) -> str:
    text = path.read_text()
    start = text.index(f'{{- define "{name}" -}}')
    end = text.index("{{- end -}}", start)
    lines = text[start:end].splitlines()[1:]
    return "\n".join(lines).strip()


def test_upsert_tls_secret_scripts_match() -> None:
    serving = _define_body(
        AI / "templates" / "_helpers.tpl",
        "pca-ai-serving.upsertTlsSecretScript",
    )
    platform = _define_body(
        PLATFORM / "templates" / "_helpers.tpl",
        "pca-platform-config.upsertTlsSecretScript",
    )
    assert serving == platform


def test_sse_http_files_match() -> None:
    assert GUARDRAILS_SSE.read_text() == ROUTER_SSE.read_text()


def test_suite_oc_modules_reexport_pca_oc() -> None:
    import sys

    tests = Path(__file__).resolve().parents[1]
    e2e = tests / "e2e"
    smoke = tests / "cluster-smoke"
    for path in (str(tests), str(e2e), str(smoke)):
        if path not in sys.path:
            sys.path.insert(0, path)
    from pca_e2e import oc as e2e_oc
    from pca_oc import OcError, http_hostname, run_oc
    from pca_smoke import oc as smoke_oc

    assert e2e_oc.OcError is OcError
    assert smoke_oc.OcError is OcError
    assert e2e_oc.run_oc is run_oc
    assert smoke_oc.run_oc is run_oc
    assert e2e_oc.http_hostname is http_hostname
    assert smoke_oc.http_hostname is http_hostname
