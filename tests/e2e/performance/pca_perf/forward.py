"""oc port-forward helper for pods or services."""

from __future__ import annotations

import socket
import subprocess
import time

from pca_e2e.oc import OcError


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class PortForward:
    """Context manager: oc port-forward <resource> local:remote."""

    def __init__(
        self,
        namespace: str,
        resource: str,
        remote_port: int,
        *,
        scheme: str = "http",
    ):
        self.namespace = namespace
        self.resource = resource  # e.g. pod/foo or svc/bar
        self.remote_port = remote_port
        self.scheme = scheme
        self.local_port = _free_port()
        self._proc: subprocess.Popen[str] | None = None

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://127.0.0.1:{self.local_port}"

    def __enter__(self) -> PortForward:
        self._proc = subprocess.Popen(
            [
                "oc",
                "port-forward",
                "-n",
                self.namespace,
                self.resource,
                f"{self.local_port}:{self.remote_port}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 45
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
            f"port-forward to {self.namespace}/{self.resource}:{self.remote_port} "
            "not ready"
        )

    def __exit__(self, *args: object) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
