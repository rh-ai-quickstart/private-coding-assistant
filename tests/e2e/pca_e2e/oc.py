"""Thin wrappers around the OpenShift CLI (`oc`)."""

from __future__ import annotations

import base64
import json
import socket
import subprocess
import time
from typing import Any


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
    result = subprocess.run(
        ["oc", *args],
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


def ensure_devworkspace_started(
    namespace: str,
    name: str,
    *,
    timeout_secs: int = 600,
) -> dict[str, Any]:
    """Patch started=true and wait until phase=Running."""
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
