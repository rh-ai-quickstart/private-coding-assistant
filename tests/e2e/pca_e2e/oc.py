"""Thin wrappers around the OpenShift CLI (`oc`)."""

from __future__ import annotations

import base64
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TypedDict

_TESTS = Path(__file__).resolve().parents[2]
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from pca_oc import (  # noqa: E402
    OcError,
    devworkspace_env,
    find_opencode_devworkspace,
    find_running_opencode_devworkspace,
    get_json,
    get_jsonpath,
    http_hostname,
    is_opencode_devworkspace,
    list_devworkspaces,
    resource_exists,
    run_oc,
    secret_data,
    whoami,
)

_http_hostname = http_hostname


class WorkspaceCurlResult(TypedDict):
    status: int
    body: str
    ttfb: float
    total: float


def is_maas_openai_base_url(base: str) -> bool:
    value = (base or "").strip()
    if not value:
        return False
    host = _http_hostname(value)
    if not host:
        return False
    extra = os.environ.get("PCA_MAAS_HOSTNAME", "").strip()
    if extra and host == _http_hostname(extra):
        return True
    if host.startswith("maas.apps."):
        return True
    label = host.split(".", 1)[0]
    return label == "maas-default-gateway" or label.startswith(
        "maas-default-gateway-"
    )


MAAS_GATEWAY_NAME = "maas-default-gateway"
MAAS_GATEWAY_NAMESPACE = "openshift-ingress"


def maas_clusterip_service_name(gateway_class: str) -> str:
    cls = (gateway_class or "").strip()
    if not cls:
        return ""
    return f"{MAAS_GATEWAY_NAME}-{cls}"


def expected_maas_clusterip_host(gateway_class: str) -> str:
    svc = maas_clusterip_service_name(gateway_class)
    if not svc:
        return ""
    return f"{svc}.{MAAS_GATEWAY_NAMESPACE}.svc.cluster.local"


def clusterip_host_matches_gateway_class(host: str, gateway_class: str) -> bool:
    expected = expected_maas_clusterip_host(gateway_class)
    return bool(expected) and (host or "").lower() == expected


def assert_openai_base_url_reaches_maas(base: str) -> None:
    """Shape check plus live Gateway class / Service for ClusterIP URLs."""
    if not is_maas_openai_base_url(base):
        raise AssertionError(
            f"OPENAI_BASE_URL must route through maas-default-gateway "
            f"(ClusterIP or maas.apps hostname), got {base!r}. "
            "Redeploy pca-devspaces so chat uses the MaaS / RHCL gateway "
            "(guardrails is an HTTPRoute backend)."
        )
    host = _http_hostname(base)
    if not host.endswith(".svc.cluster.local"):
        return
    cls = get_jsonpath(
        "gateway",
        MAAS_GATEWAY_NAME,
        "{.spec.gatewayClassName}",
        namespace=MAAS_GATEWAY_NAMESPACE,
    )
    expected = expected_maas_clusterip_host(cls)
    if host != expected:
        raise AssertionError(
            f"OPENAI_BASE_URL host {host!r} does not match live Gateway "
            f"{MAAS_GATEWAY_NAMESPACE}/{MAAS_GATEWAY_NAME} class {cls!r} "
            f"(expected {expected!r})"
        )
    svc = maas_clusterip_service_name(cls)
    if not resource_exists("svc", svc, namespace=MAAS_GATEWAY_NAMESPACE):
        raise AssertionError(
            f"Service {MAAS_GATEWAY_NAMESPACE}/{svc} missing for "
            f"OPENAI_BASE_URL {base!r}"
        )


def devworkspace_is_running(devworkspace: dict[str, Any]) -> bool:
    """True when spec.started and status.phase are already Running."""
    started = (devworkspace.get("spec") or {}).get("started")
    phase = (devworkspace.get("status") or {}).get("phase") or ""
    return bool(started) and phase == "Running"


def ensure_devworkspace_started(
    namespace: str,
    name: str,
    *,
    timeout_secs: int = 600,
) -> dict[str, Any]:
    """Patch started=true and wait until phase=Running.

    Skip the patch when the workspace is already Running. A no-op patch
    still writes the object and can kick the DevWorkspace controller.
    """
    dw = get_json("devworkspace", name, namespace=namespace)
    if devworkspace_is_running(dw):
        return dw
    run_oc(
        "patch",
        "devworkspace",
        name,
        "-n",
        namespace,
        "--type=merge",
        "-p",
        '{"spec":{"started":true}}',
    )
    deadline = time.time() + timeout_secs
    last_phase = ""
    while time.time() < deadline:
        dw = get_json("devworkspace", name, namespace=namespace)
        last_phase = (dw.get("status") or {}).get("phase") or ""
        if last_phase == "Running":
            return dw
        if last_phase in {"Failed", "Error"}:
            raise OcError(f"DevWorkspace {namespace}/{name} entered {last_phase}")
        time.sleep(5)
    raise OcError(
        f"DevWorkspace {namespace}/{name} not Running within {timeout_secs}s "
        f"(last phase={last_phase!r})"
    )


def find_workspace_pod(namespace: str, workspace_id: str) -> str:
    result = run_oc(
        "get",
        "pods",
        "-n",
        namespace,
        "-l",
        f"controller.devfile.io/devworkspace_id={workspace_id}",
        "-o",
        "json",
        check=False,
    )
    if result.returncode != 0:
        raise OcError(f"cannot list pods for workspace {workspace_id}: {result.stderr}")
    items = json.loads(result.stdout or "{}").get("items") or []
    for item in items:
        if (item.get("status") or {}).get("phase") == "Running":
            name = (item.get("metadata") or {}).get("name")
            if name:
                return str(name)
    raise OcError(f"no Running pod for workspace id {workspace_id} in {namespace}")


def _dev_tools_container(namespace: str, pod: str) -> str | None:
    names = get_jsonpath(
        "pod", pod, "{.spec.containers[*].name}", namespace=namespace
    ).split()
    if "dev-tools" in names:
        return "dev-tools"
    return names[0] if names else None


def exec_in_pod(
    namespace: str,
    pod: str,
    *command: str,
    container: str | None = None,
    timeout: int = 120,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command in the workspace pod. Pass argv as *command (e.g. bash -lc '...')."""
    if container is None:
        container = _dev_tools_container(namespace, pod)
    args = ["exec", "-n", namespace, pod]
    if container:
        args.extend(["-c", container])
    args.append("--")
    args.extend(command)
    return run_oc(*args, check=check, timeout=timeout)


PCA_E2E_BODY_MARKER = "---PCA_E2E_BODY---\n"


def workspace_curl_script(
    *,
    path: str,
    method: str,
    body_b64: str,
    timeout: int,
) -> str:
    if not path.startswith("/") or "\n" in path or "\r" in path:
        raise OcError(f"path must be a single-line absolute path, got {path!r}")
    quoted_path = shlex.quote(path)
    return f"""
set -euo pipefail
test -n "${{OPENAI_BASE_URL:-}}" || {{ echo "missing OPENAI_BASE_URL" >&2; exit 2; }}
test -n "${{OPENAI_API_KEY:-}}" || {{ echo "missing OPENAI_API_KEY" >&2; exit 2; }}
base="${{OPENAI_BASE_URL}}"
while [[ "$base" == */ ]]; do
  base="${{base%/}}"
done
origin="$base"
if [[ "$base" == */v1 ]]; then
  origin="${{base%/v1}}"
fi
url="${{origin}}"{quoted_path}
body_file=$(mktemp /tmp/pca-e2e-body.XXXXXX)
req_file=$(mktemp /tmp/pca-e2e-req.XXXXXX)
args=(curl -k -sS -o "$body_file"
  -w '%{{http_code}} %{{time_starttransfer}} %{{time_total}}'
  --max-time {int(timeout)}
  -X {shlex.quote(method.upper())}
  -H "Authorization: Bearer ${{OPENAI_API_KEY}}"
  "$url")
body_b64={shlex.quote(body_b64)}
if [ -n "$body_b64" ]; then
  printf '%s' "$body_b64" | base64 -d > "$req_file"
  args+=(-H "Content-Type: application/json" --data-binary @"$req_file")
fi
metrics="$("${{args[@]}}")"
echo "$metrics"
echo '---PCA_E2E_BODY---'
cat "$body_file"
"""


def parse_workspace_curl_output(text: str) -> WorkspaceCurlResult:
    marker = PCA_E2E_BODY_MARKER
    if marker not in text:
        raise OcError(
            f"workspace_openai_curl missing body marker: {text[:300]!r}"
        )
    metrics_line, body = text.split(marker, 1)
    parts = metrics_line.strip().split()
    if len(parts) != 3:
        raise OcError(f"workspace_openai_curl bad metrics: {metrics_line!r}")
    try:
        status = int(parts[0])
        ttfb = float(parts[1])
        total = float(parts[2])
    except ValueError as exc:
        raise OcError(
            f"workspace_openai_curl bad metrics: {metrics_line!r}"
        ) from exc
    return {"status": status, "body": body, "ttfb": ttfb, "total": total}


def workspace_openai_curl(
    namespace: str,
    pod: str,
    *,
    path: str,
    method: str = "POST",
    json_body: dict[str, Any] | None = None,
    timeout: int = 90,
) -> WorkspaceCurlResult:
    body_b64 = ""
    if json_body is not None:
        body_b64 = base64.b64encode(
            json.dumps(json_body).encode("utf-8")
        ).decode("ascii")
    script = workspace_curl_script(
        path=path,
        method=method,
        body_b64=body_b64,
        timeout=timeout,
    )
    result = exec_in_pod(
        namespace,
        pod,
        "bash",
        "-lc",
        script,
        timeout=timeout + 30,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:500]
        raise OcError(
            f"workspace_openai_curl {method.upper()} {path} failed "
            f"(rc={result.returncode}): {err}"
        )
    return parse_workspace_curl_output(result.stdout or "")


def oc_cp_to_pod(
    local_path: str,
    namespace: str,
    pod: str,
    remote_path: str,
    *,
    container: str | None = None,
    timeout: int = 120,
) -> None:
    if container is None:
        container = _dev_tools_container(namespace, pod)
    dest = f"{namespace}/{pod}:{remote_path}"
    args = ["cp", local_path, dest, "-n", namespace]
    if container:
        args.extend(["-c", container])
    run_oc(*args, timeout=timeout)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class PortForward:
    """Context manager: oc port-forward pod local_port:remote_port."""

    def __init__(self, namespace: str, pod: str, remote_port: int = 4096):
        self.namespace = namespace
        self.pod = pod
        self.remote_port = remote_port
        self.local_port = _free_port()
        self._proc: subprocess.Popen[str] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.local_port}"

    def __enter__(self) -> PortForward:
        self._proc = subprocess.Popen(
            [
                "oc",
                "port-forward",
                "-n",
                self.namespace,
                f"pod/{self.pod}",
                f"{self.local_port}:{self.remote_port}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._proc.poll() is not None:
                out = self._proc.stdout.read() if self._proc.stdout else ""
                raise OcError(f"port-forward exited early: {out}")
            try:
                with socket.create_connection(("127.0.0.1", self.local_port), timeout=1):
                    return self
            except OSError:
                time.sleep(0.2)
        raise OcError(
            f"port-forward to {self.namespace}/{self.pod}:{self.remote_port} not ready"
        )

    def __exit__(self, *args: object) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
