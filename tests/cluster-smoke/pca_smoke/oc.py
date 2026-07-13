"""Thin wrappers around the OpenShift CLI (`oc`)."""

from __future__ import annotations

import base64
import json
import re
import shlex
import subprocess
import uuid
from typing import Any


class OcError(RuntimeError):
    def __init__(self, message: str, *, stdout: str = "", stderr: str = "", returncode: int = 1):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def run_oc(
    *args: str,
    check: bool = True,
    timeout: int = 120,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = ["oc", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
        check=False,
    )
    if check and result.returncode != 0:
        raise OcError(
            f"oc {' '.join(args)} failed (rc={result.returncode}): {result.stderr.strip()}",
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )
    return result


def whoami() -> str:
    return run_oc("whoami").stdout.strip()


def resource_exists(resource: str, name: str, namespace: str | None = None) -> bool:
    args = ["get", resource, name, "-o", "name"]
    if namespace:
        args.extend(["-n", namespace])
    result = run_oc(*args, check=False)
    return result.returncode == 0


def get_json(resource: str, name: str, namespace: str | None = None) -> dict[str, Any]:
    args = ["get", resource, name, "-o", "json"]
    if namespace:
        args.extend(["-n", namespace])
    return json.loads(run_oc(*args).stdout)


def get_jsonpath(
    resource: str,
    name: str,
    jsonpath: str,
    namespace: str | None = None,
) -> str:
    args = ["get", resource, name, "-o", f"jsonpath={jsonpath}"]
    if namespace:
        args.extend(["-n", namespace])
    return run_oc(*args).stdout.strip()


def secret_data(name: str, key: str, namespace: str) -> str:
    data = get_json("secret", name, namespace=namespace).get("data") or {}
    b64 = data.get(key)
    if not b64:
        raise OcError(f"secret/{name} key {key} is empty in {namespace}")
    return base64.b64decode(b64).decode("utf-8")


def condition_status(
    resource: str,
    name: str,
    condition_type: str,
    namespace: str,
) -> str | None:
    obj = get_json(resource, name, namespace=namespace)
    for cond in obj.get("status", {}).get("conditions", []) or []:
        if cond.get("type") == condition_type:
            return cond.get("status")
    return None


def deployment_available(name: str, namespace: str) -> bool:
    if not resource_exists("deploy", name, namespace=namespace):
        return False
    ready = get_jsonpath(
        "deploy",
        name,
        "{.status.conditions[?(@.type=='Available')].status}",
        namespace=namespace,
    )
    return ready == "True"


def pvc_phase(name: str, namespace: str) -> str:
    return get_jsonpath("pvc", name, "{.status.phase}", namespace=namespace)


def route_host(name: str, namespace: str) -> str:
    return get_jsonpath("route", name, "{.spec.host}", namespace=namespace)


def configmap_data(name: str, namespace: str) -> dict[str, str]:
    obj = get_json("configmap", name, namespace=namespace)
    return obj.get("data") or {}


def in_cluster_http(
    namespace: str,
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    insecure: bool = True,
    timeout_secs: int = 120,
) -> tuple[int, Any]:
    """HTTP from an ephemeral curl pod. Returns (status_code, parsed_json_or_text)."""
    script_parts = [
        "curl",
        "-sS",
        "-o",
        "/tmp/body",
        "-w",
        "%{http_code}",
        "--max-time",
        str(timeout_secs),
    ]
    if insecure:
        script_parts.append("-k")
    script_parts.extend(["-X", method, url])
    for key, value in (headers or {}).items():
        script_parts.extend(["-H", f"{key}: {value}"])
    if json_body is not None:
        script_parts.extend(
            ["-H", "Content-Type: application/json", "-d", json.dumps(json_body)]
        )

    inner = " ".join(shlex.quote(p) for p in script_parts)
    shell_cmd = f"code=$({inner}); echo \"$code\"; cat /tmp/body"

    pod = f"pca-smoke-{uuid.uuid4().hex[:10]}"
    run_oc("delete", "pod", pod, "-n", namespace, "--ignore-not-found", check=False)

    args = [
        "run",
        pod,
        "--rm",
        "-i",
        "--restart=Never",
        "-n",
        namespace,
        "--image=curlimages/curl:8.5.0",
        "--command",
        "--",
        "sh",
        "-c",
        shell_cmd,
    ]
    result = run_oc(*args, check=False, timeout=timeout_secs + 60)
    text = result.stdout
    if not text.strip():
        raise OcError(
            f"empty response from in-cluster request to {url}",
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    status: int | None = None
    body_start = 0
    for i, line in enumerate(text.splitlines()):
        if line.strip().isdigit() and len(line.strip()) == 3:
            status = int(line.strip())
            body_start = i + 1
            break
    if status is None:
        raise OcError(
            f"could not parse HTTP status from curl output for {url}: {text[:300]!r}",
            stdout=result.stdout,
            stderr=result.stderr,
        )
    body = "\n".join(text.splitlines()[body_start:])
    # `oc run --rm` appends: pod "name" deleted
    body = _strip_oc_run_trailer(body)
    try:
        parsed: Any = json.loads(body) if body.strip() else None
    except json.JSONDecodeError:
        parsed = body
    return status, parsed


def _strip_oc_run_trailer(body: str) -> str:
    """Remove trailing `pod \"...\" deleted` that `oc run --rm` appends to stdout."""
    return re.sub(r'\s*pod "[^"]+" deleted\s*$', "", body).rstrip()


def message_text(choice_or_message: dict[str, Any]) -> str:
    """Extract assistant text from a chat choice (content or reasoning)."""
    msg = choice_or_message.get("message") or choice_or_message
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content
    reasoning = msg.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    return content or reasoning or ""
