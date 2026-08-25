"""Shared OpenShift CLI wrappers for e2e and cluster-smoke."""

from __future__ import annotations

import base64
import json
import subprocess
from typing import Any
from urllib.parse import urlparse


class OcError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 1,
    ):
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
    try:
        result = subprocess.run(
            ["oc", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        raise OcError(
            f"oc {' '.join(args)} timed out after {timeout} seconds",
            stdout=stdout,
            stderr=stderr,
            returncode=-1,
        ) from exc
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
    return run_oc(*args, check=False).returncode == 0


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


def list_devworkspaces(namespace: str) -> list[dict[str, Any]]:
    result = run_oc("get", "devworkspace", "-n", namespace, "-o", "json", check=False)
    if result.returncode != 0:
        return []
    try:
        return list((json.loads(result.stdout).get("items") or []))
    except json.JSONDecodeError:
        return []


def is_opencode_devworkspace(devworkspace: dict[str, Any]) -> bool:
    name = (devworkspace.get("metadata") or {}).get("name") or ""
    if "opencode" in name.lower():
        return True
    for component in (
        (devworkspace.get("spec") or {}).get("template") or {}
    ).get("components") or []:
        image = ((component.get("container") or {}).get("image") or "")
        if "devspaces-opencode" in image or "/opencode" in image:
            return True
    return False


def find_opencode_devworkspace(namespace: str) -> dict[str, Any] | None:
    for item in list_devworkspaces(namespace):
        if is_opencode_devworkspace(item):
            return item
    return None


def find_running_opencode_devworkspace(namespace: str) -> dict[str, Any] | None:
    for item in list_devworkspaces(namespace):
        if not is_opencode_devworkspace(item):
            continue
        phase = (item.get("status") or {}).get("phase") or ""
        if phase == "Running":
            return item
    return None


def devworkspace_env(devworkspace: dict[str, Any]) -> dict[str, str]:
    """Flatten container env name→value from a DevWorkspace spec."""
    env: dict[str, str] = {}
    for component in (
        (devworkspace.get("spec") or {}).get("template") or {}
    ).get("components") or []:
        for entry in (component.get("container") or {}).get("env") or []:
            name = entry.get("name")
            if not name or "value" not in entry:
                continue
            env[str(name)] = str(entry.get("value") or "")
    return env


def http_hostname(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").lower()
