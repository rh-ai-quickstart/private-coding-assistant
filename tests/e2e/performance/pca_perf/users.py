"""Require pre-deployed OpenCode DevSpaces for the ladder."""

from __future__ import annotations

from pca_e2e import oc

from pca_perf.config import AI_GATEWAY_APIKEY_KEY, AI_GATEWAY_APIKEY_SECRET, user_namespace


def require_opencode_users(max_n: int) -> list[str]:
    """Return namespaces for dev-user1..max_n or raise OcError with a clear message."""
    missing: list[str] = []
    details: list[str] = []
    namespaces: list[str] = []

    for i in range(1, max_n + 1):
        ns = user_namespace(i)
        namespaces.append(ns)
        problems: list[str] = []
        if not oc.resource_exists("namespace", ns):
            problems.append("namespace missing")
        else:
            dw = oc.find_opencode_devworkspace(ns)
            if dw is None:
                problems.append("no OpenCode DevWorkspace")
            if not oc.resource_exists("secret", "opencode-web-password", namespace=ns):
                problems.append("secret/opencode-web-password missing")
            if not oc.resource_exists(
                "secret", AI_GATEWAY_APIKEY_SECRET, namespace=ns
            ):
                problems.append(f"secret/{AI_GATEWAY_APIKEY_SECRET} missing")
            else:
                try:
                    key = oc.secret_data(
                        AI_GATEWAY_APIKEY_SECRET, AI_GATEWAY_APIKEY_KEY, ns
                    )
                    if not key.strip():
                        problems.append(f"secret/{AI_GATEWAY_APIKEY_SECRET} empty")
                except oc.OcError as exc:
                    problems.append(str(exc))
        if problems:
            missing.append(ns)
            details.append(f"  - {ns}: {', '.join(problems)}")

    if missing:
        needed = ", ".join(missing)
        raise oc.OcError(
            f"Performance ladder needs {max_n} OpenCode DevSpace(s) "
            f"(dev-user1..dev-user{max_n}), but these are not ready:\n"
            + "\n".join(details)
            + "\n\nDeploy them first, then re-run:\n"
            f"  make devspace-deploy-existing-openshift N={max_n} TYPE=opencode\n"
            f"Missing/incomplete: {needed}"
        )
    return namespaces


def api_key_for_namespace(namespace: str) -> str:
    return oc.secret_data(
        AI_GATEWAY_APIKEY_SECRET, AI_GATEWAY_APIKEY_KEY, namespace
    )
