"""OpenCode e2e: clone calculator → agent adds power → unittest proves 2**4 == 16.

Uses the OpenCode HTTP API (same server as the Web UI) with the deployed
workspace config — does not rewrite opencode.json or restart the server.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from pca_e2e import oc
from pca_e2e import opencode as ocapi

pytestmark = pytest.mark.opencode_calculator

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "simple-calculator"
PROJECT_NAME = "simple-calculator"
REMOTE_SRC = f"/tmp/{PROJECT_NAME}-src"
REMOTE_CLONE = f"/projects/{PROJECT_NAME}"


def _git_init_fixture(src: Path) -> Path:
    """Copy fixture into a temp git repo and return that path."""
    tmp = Path(tempfile.mkdtemp(prefix="pca-e2e-calc-"))
    dest = tmp / PROJECT_NAME
    shutil.copytree(src, dest)
    subprocess.run(["git", "init"], cwd=dest, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=dest, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=e2e@pca.local",
            "-c",
            "user.name=pca-e2e",
            "commit",
            "-m",
            "init simple calculator",
        ],
        cwd=dest,
        check=True,
        capture_output=True,
    )
    return dest


def _seed_and_clone(namespace: str, pod: str, local_repo: Path) -> None:
    oc.exec_in_pod(
        namespace,
        pod,
        "bash",
        "-lc",
        f"rm -rf {REMOTE_SRC} {REMOTE_CLONE} && mkdir -p {REMOTE_SRC}",
        timeout=60,
    )
    oc.oc_cp_to_pod(str(local_repo), namespace, pod, REMOTE_SRC)
    oc.exec_in_pod(
        namespace,
        pod,
        "bash",
        "-lc",
        f"""
set -euo pipefail
if [ -d {REMOTE_SRC}/{PROJECT_NAME}/.git ]; then
  SRC={REMOTE_SRC}/{PROJECT_NAME}
elif [ -d {REMOTE_SRC}/.git ]; then
  SRC={REMOTE_SRC}
else
  echo "fixture git repo not found under {REMOTE_SRC}" >&2
  find {REMOTE_SRC} -maxdepth 3 -type d -name .git >&2 || true
  exit 1
fi
git clone "$SRC" {REMOTE_CLONE}
test -f {REMOTE_CLONE}/calculator.py
cd {REMOTE_CLONE}
# Baseline: only ops that exist before the agent adds power() (power tests are in the fixture).
python3 -m unittest \
  test_calculator.TestCalculator.test_add \
  test_calculator.TestCalculator.test_subtract \
  test_calculator.TestCalculator.test_multiply \
  test_calculator.TestCalculator.test_divide \
  test_calculator.TestCalculator.test_divide_by_zero \
  -v
""",
        timeout=120,
    )


def _read_remote_file(namespace: str, pod: str, path: str) -> str:
    result = oc.exec_in_pod(namespace, pod, "bash", "-lc", f"cat {path}", timeout=30)
    return result.stdout or ""


def _running_workspace_pod(namespace: str, dw: dict) -> str:
    wid = (dw.get("status") or {}).get("devworkspaceId") or ""
    if wid:
        try:
            return oc.find_workspace_pod(namespace, wid)
        except oc.OcError:
            pass
    result = oc.run_oc("get", "pods", "-n", namespace, "-o", "json", check=False)
    items = json.loads(result.stdout or "{}").get("items") or []
    for item in items:
        if (item.get("status") or {}).get("phase") != "Running":
            continue
        name = (item.get("metadata") or {}).get("name") or ""
        if name.startswith("workspace"):
            return name
    raise oc.OcError(f"no Running workspace pod in {namespace}")


def _run_unittest(namespace: str, pod: str) -> str:
    result = oc.exec_in_pod(
        namespace,
        pod,
        "bash",
        "-lc",
        f"cd {REMOTE_CLONE} && python3 -m unittest test_calculator.py -v",
        timeout=120,
        check=False,
    )
    return f"{result.stdout}\n{result.stderr}", result.returncode


def _fail_with_session_context(
    client: ocapi.OpenCodeClient,
    session_id: str,
    message: str,
    response: dict[str, Any] | None = None,
) -> None:
    """pytest.fail with assistant text + session diff for debugging."""
    bits = [message]
    if response is not None:
        bits.append(f"assistant:\n{ocapi.message_text(response)[:1500] or '(empty)'}")
        err = (response.get("info") or {}).get("error")
        if err:
            bits.append(f"info.error: {err!r}")
    try:
        diff = client.session_diff(session_id)
        bits.append(f"session diff:\n{json.dumps(diff, indent=2)[:2000]}")
    except Exception as exc:  # noqa: BLE001 — best-effort diagnostics
        bits.append(f"session diff unavailable: {exc}")
    pytest.fail("\n\n".join(bits))


def test_opencode_adds_power_and_unittest_passes(require_dev_namespace: str) -> None:
    ns = require_dev_namespace
    oc.whoami()

    dw = oc.find_opencode_devworkspace(ns)
    assert dw is not None, (
        f"no OpenCode DevWorkspace in {ns} — OpenCode must be deployed "
        f"(make e2e assumes TYPE=opencode / OpenCode DW present)"
    )

    name = (dw.get("metadata") or {}).get("name") or ""
    assert name, "DevWorkspace missing metadata.name"

    assert oc.resource_exists(
        "secret", "opencode-web-password", namespace=ns
    ), f"secret/opencode-web-password missing in {ns}"

    password = oc.secret_data("opencode-web-password", "password", ns)
    assert password.strip(), "opencode-web-password is empty"

    dw = oc.ensure_devworkspace_started(ns, name, timeout_secs=600)
    pod = _running_workspace_pod(ns, dw)

    local_repo = _git_init_fixture(FIXTURE_DIR)
    try:
        _seed_and_clone(ns, pod, local_repo)
    finally:
        shutil.rmtree(local_repo.parent, ignore_errors=True)

    provider_id, model_id = ocapi.resolve_model_ids(ns, pod)

    # Port-forward avoids OpenShift Route idle timeouts on long agent turns.
    with oc.PortForward(ns, pod, 4096) as pf:
        with ocapi.OpenCodeClient(
            pf.base_url, password, directory=REMOTE_CLONE, timeout_secs=120
        ) as client:
            client.health()
            session = client.create_session("pca-e2e-calculator-power")
            sid = session["id"]

            turn1 = (
                f"You are working in {REMOTE_CLONE}. "
                "test_calculator.py already imports power and asserts "
                "power(2, 4) == 16 and power(3, 2) == 9, but calculator.py has no power yet. "
                "Edit calculator.py only: add `def power(base, exponent):` that returns "
                "base ** exponent for non-negative integer exponents. "
                "Do not remove existing functions. Do not ask questions — make the edit."
            )
            try:
                resp1 = client.send_message(
                    sid, turn1, provider_id=provider_id, model_id=model_id, timeout=900
                )
            except ocapi.OpenCodeError as exc:
                _fail_with_session_context(client, sid, f"turn1 OpenCode error: {exc}")

            calc_after_t1 = _read_remote_file(ns, pod, f"{REMOTE_CLONE}/calculator.py")
            if not re.search(r"\bdef\s+power\s*\(", calc_after_t1):
                _fail_with_session_context(
                    client,
                    sid,
                    f"turn1: power() missing from calculator.py:\n{calc_after_t1}",
                    resp1,
                )

            turn2 = (
                f"Still in {REMOTE_CLONE}. Run "
                "`python3 -m unittest test_calculator.py -v` and fix calculator.py "
                "until every test passes (especially the power cases). "
                "Do not ask questions."
            )
            try:
                resp2 = client.send_message(
                    sid, turn2, provider_id=provider_id, model_id=model_id, timeout=900
                )
            except ocapi.OpenCodeError as exc:
                _fail_with_session_context(client, sid, f"turn2 OpenCode error: {exc}")

            out2, rc2 = _run_unittest(ns, pod)
            if rc2 != 0:
                _fail_with_session_context(
                    client,
                    sid,
                    f"turn2: unittest still failing (rc={rc2}):\n{out2}",
                    resp2,
                )

            turn3 = (
                "In one short sentence: what does power(2, 4) return in this project?"
            )
            try:
                resp3 = client.send_message(
                    sid, turn3, provider_id=provider_id, model_id=model_id, timeout=900
                )
            except ocapi.OpenCodeError as exc:
                _fail_with_session_context(client, sid, f"turn3 OpenCode error: {exc}")
            if not ocapi.message_text(resp3).strip():
                _fail_with_session_context(
                    client, sid, "turn3: empty confirm reply", resp3
                )

    # Final hard proof (independent of chat text).
    calc_src = _read_remote_file(ns, pod, f"{REMOTE_CLONE}/calculator.py")
    assert re.search(r"\bdef\s+power\s*\(", calc_src), (
        f"power() not found in calculator.py:\n{calc_src}"
    )

    out, rc = _run_unittest(ns, pod)
    assert rc == 0, f"unittest failed:\n{out}"
    assert "OK" in out or "ok" in out, out

    probe = oc.exec_in_pod(
        ns,
        pod,
        "bash",
        "-lc",
        f"cd {REMOTE_CLONE} && python3 -c "
        "'import calculator; assert calculator.power(2, 4) == 16; "
        "assert calculator.power(3, 2) == 9; print(\"power-ok\")'",
        timeout=60,
        check=False,
    )
    assert probe.returncode == 0, f"power probe failed:\n{probe.stdout}\n{probe.stderr}"
    assert "power-ok" in (probe.stdout or "")
