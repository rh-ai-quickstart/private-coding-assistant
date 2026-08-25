"""Thin wrappers around the OpenShift CLI (`oc`)."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

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


def list_resource_names(
    resource: str,
    namespace: str,
    *,
    label_selector: str | None = None,
) -> list[str]:
    args = ["get", resource, "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"]
    if label_selector:
        args.extend(["-l", label_selector])
    result = run_oc(*args, check=False)
    if result.returncode != 0:
        return []
    return [n for n in result.stdout.split() if n]


def in_cluster_http_shell(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    insecure: bool = True,
    timeout_secs: int = 120,
    body_path: str | None = None,
) -> str:
    """Build the in-pod curl script. Unique body_path avoids xdist /tmp races."""
    if body_path is None:
        body_path = f"/tmp/pca-smoke-{uuid.uuid4().hex[:12]}"
    script_parts = [
        "curl",
        "-sS",
        "-o",
        body_path,
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
    quoted_body = shlex.quote(body_path)
    return (
        f"code=$({inner}) || true; echo \"$code\"; "
        f"if [ -f {quoted_body} ]; then cat {quoted_body}; fi"
    )


def parse_in_cluster_http_output(
    stdout: str,
    stderr: str = "",
    *,
    url: str = "",
) -> tuple[int, Any]:
    """Parse oc-run curl stdout. Missing body is not an error; use stderr."""
    text = stdout or ""
    status: int | None = None
    body_start = 0
    for i, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if stripped.isdigit() and len(stripped) == 3:
            status = int(stripped)
            body_start = i + 1
            break
    if status is None:
        err = (stderr or "").strip() or text.strip()
        if not err:
            raise OcError(
                f"empty response from in-cluster request to {url}",
                stdout=stdout,
                stderr=stderr,
            )
        return 0, err
    body = "\n".join(text.splitlines()[body_start:])
    body = _strip_oc_run_trailer(body)
    if not body.strip():
        err = (stderr or "").strip()
        return status, err if err else None
    try:
        parsed: Any = json.loads(body)
    except json.JSONDecodeError:
        parsed = body
    return status, parsed


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
    shell_cmd = in_cluster_http_shell(
        url,
        method=method,
        headers=headers,
        json_body=json_body,
        insecure=insecure,
        timeout_secs=timeout_secs,
    )

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
    if not (result.stdout or "").strip() and not (result.stderr or "").strip():
        raise OcError(
            f"empty response from in-cluster request to {url}",
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )
    return parse_in_cluster_http_output(
        result.stdout, result.stderr, url=url
    )


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
