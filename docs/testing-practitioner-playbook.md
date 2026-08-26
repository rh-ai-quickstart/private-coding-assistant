# Testing, explained (with this repo)

This is a learning guide based on the **ISTQB Certified Tester Foundation Level Syllabus v4.0.1**. It follows the book’s order so you can map ideas back to the PDF, but it is written for understanding — not for an exam.

You do not need testing jargon yet. Whenever a formal term appears, you’ll get the meaning the syllabus uses, then what that looks like in *Private AI Coding Assistant* (`make unit`, `make smoke`, Helm charts, the AI gateway path).

**What we left thin on purpose:** exam rules, formal review-meeting theater, estimation formulas, and long tool taxonomies. The ideas stay; the paperwork does not.

---

## Before chapter 1 — how testing shows up here

Traffic in this project roughly goes:

```text
DevSpaces IDE → maas-default-gateway (MaaS / RHCL) → llm-d → vLLM
```

Two commands matter immediately:

```bash
make unit    # small Python checks, no cluster
make smoke   # checks a real OpenShift deploy (needs oc login)
```

- **Unit tests** live in `tests/unit/`. Today they mostly exercise `pca_langfuse_io.py` (parse token usage from model responses).
- **Smoke tests** live in `tests/cluster-smoke/` (`make smoke`). They are **not** a separate ISTQB test level — they are a thin **system** (and sometimes **system integration**) suite: Ready conditions, `/v1/models`, chat, gateway API keys, optional Grafana/Langfuse/DevSpaces. See [Smoke testing](#smoke-testing-under-system--sometimes-system-integration).

Hold that picture. The rest of the guide is “why those kinds of checks exist, and when you’d pick one over another.”

If a word feels fuzzy (defect, failure, test case…), jump to [Core definitions](#core-definitions-learn-these-words-first) below, then come back.

---

# Core definitions (learn these words first)

These are the words the syllabus expects you to tell apart. For each one: the meaning (aligned with ISTQB CTFL v4.0.1), a plain restatement, and an example from this repo.

### Error

**Definition:** An **error** is a human mistake — something a person did wrong (the syllabus also calls these mistakes).

**In plain words:** The slip in a person’s head or hands.

**Example:** A developer types the wrong default for `aiGateway.enabled`, or forgets that ARO needs `managed-csi` instead of the AWS storage class.

### Defect (also called fault or bug)

**Definition:** A **defect** is a flaw (fault, bug) in a work product — documentation, source code, a build file, a test script, a Helm chart, and so on. Humans make errors, which *produce* defects. Defects found early (e.g. in a values file) often cause more defects later if nobody catches them.

**In plain words:** The wrong thing sitting in the artifact — even if nobody has hit it yet.

**Example:** The chart renders a Gateway without an AuthPolicy. That missing/wrong config *is* the defect. It lives in YAML whether or not anyone has called the API yet.

**Important:** Not every defect always causes a failure. Some only fail in special conditions; some may never be executed.

### Failure

**Definition:** A **failure** is when the system, while running, does not do what it should — or does something it should not. In dynamic testing, executing a defect in code *may* cause a failure.

**In plain words:** What you observe going wrong when the system runs.

**Example:** Smoke posts chat/completions without an API key and gets `200` instead of `401`/`403`. That wrong runtime behavior is the failure. (The defect was the broken/missing auth config or policy.)

**Also:** Failures are not only from code defects. The environment can cause failures too (bad cluster networking, GPU node pressure, missing CRDs).

### Root cause

**Definition:** A **root cause** is a fundamental reason a problem occurred (for example, a situation that led to an error). You find it with root-cause analysis when a failure happens or a defect is found — so you can prevent the *same class* of problem again, not only patch the symptom.

**In plain words:** Why this kind of mistake kept happening — deeper than the one-line fix.

**Example:** Failure: IDE cannot chat. Defect: AuthPolicy missing. Root cause: existing OpenShift install skipped confirming `authpolicies.kuadrant.io`, so the chart’s auth pieces never became real.

### How error → defect → failure fit together

```text
Person makes an ERROR (mistake)
        ↓
leaves a DEFECT in a work product (bug in code/chart/docs)
        ↓
when that defect is exercised at runtime → FAILURE (system misbehaves)
        ↓
ROOT CAUSE = deeper reason the error happened (process, knowledge, tools, time pressure…)
```

| Term | Lives in… | You notice it when… |
|------|-----------|---------------------|
| Error | a person’s action | you reconstruct “who/what went wrong in the work” |
| Defect | the artifact (code, YAML, docs) | review, static analysis, or later when it fails |
| Failure | a running system | smoke turns red, demo breaks, user complains |
| Root cause | the surrounding why | you ask “how do we stop this class of bug?” |

### Testing, test object, quality

**Testing** — a set of activities to discover defects and evaluate the quality of software work products.

**Test object** — the work product being tested (a function, a chart, a namespace, the whole stack).

**Quality** — (in everyday syllabus use) how good the test object is relative to needs/requirements — testing helps you *assess* that and reduce risk of failure in operation.

**Example:** For `make unit`, the test object is mostly `pca_langfuse_io.py`. For `make smoke`, the test object is the deployed OpenShift stack in `AI_NAMESPACE`.

### Verification vs validation

**Verification** — checking whether the system meets *specified* requirements (“did we build it as specified?”).

**Validation** — checking whether the system meets users’ and other stakeholders’ needs in its operational environment (“did we build the right thing?”).

**Example:** Verification: AuthPolicy rejects missing keys (as designed). Validation: a real developer in DevSpaces can complete a coding chat through `maas-default-gateway` and get useful work done.

### Static vs dynamic testing

**Static testing** — testing *without* executing the software (reviews, static analysis). It can find defects directly; it does not cause failures.

**Dynamic testing** — testing *by executing* the software. It can trigger failures caused by defects.

**Example:** Static — reading `values-aro.yaml` in a PR. Dynamic — `make smoke COMPONENT=vllm`.

### Debugging (not the same as testing)

**Debugging** — finding the causes of a failure (the defects), analyzing them, and eliminating them. Typical loop after a dynamic failure: reproduce → diagnose (find defect) → fix. Testing may *trigger* the failure; debugging *removes* the defect.

### Expected result, actual result, anomaly

**Expected result** — what should happen if the system is correct (status `401`, PVC `Bound`, usage dict with `input/output/total`).

**Actual result** — what really happened when you ran the check.

**Anomaly** — something observed that differs from expectations (the syllabus uses this especially in reviews/execution). Not every anomaly is instantly labeled “defect”; you analyze it. In pytest terms: an assertion failure is how we usually flag “actual ≠ expected.”

**Example:** Expected `status in (401, 403)`; actual `200` → anomaly / failing test → then you hunt the defect.

### Test basis, test condition, test case, coverage

**Test basis** — the body of knowledge you derive tests from (requirements, user stories, risks, architecture, known bugs, acceptance criteria…).

**Test condition** — something that can be verified — a testable aspect of the test basis (“missing API key must be rejected,” “LLMIS must be Ready”). Analysis answers “what to test?” with conditions and coverage ideas.

**Test case** — a concrete check designed from conditions: inputs, steps/preconditions, and expected results (in code: a `test_…` function with asserts).

**Coverage** — how much of something you exercised (requirements, partitions, branches, states…), usually thought of as “exercised / total,” often as a percentage.

**Example:**

- Test basis: “RHCL front door requires per-DevSpace API keys.”
- Test condition: “invalid bearer token is rejected.”
- Test case: `test_chat_completions_rejects_invalid_api_key` in `test_ai_gateway.py`.
- Coverage: you also need the “missing” and “valid” partitions, or auth coverage is incomplete.

### Testware, test data, test result

**Testware** — work products produced for testing (plans, cases, scripts, fixtures, logs, defect reports…).

**Test data** — data used to execute tests (model id, API key from a Secret, JSON bodies).

**Test result** — outcome of execution (pass/fail/skip, plus logs). Actual results are compared with expected results.

**Example:** `conftest.py` fixtures, `tests/cluster-smoke/*.py`, and pytest output are testware / results. The bearer token read from `pca-maas-apikey` is test data.

More terms (levels, types, techniques) are defined when their chapters appear; the big glossary at the end collects them.

---

# Chapter 1 — Fundamentals of testing

## What testing actually is

People often think testing means “run the program and see if it crashes.” The syllabus is broader: **software testing is a set of activities to discover defects and evaluate the quality of software work products.** Whatever you’re examining is the **test object**.

So the test object might be a Python function, a Helm chart, a Gateway CR, or the whole AI-serving namespace. Testing also includes deciding what to check, designing cases, preparing data, running checks, and wrapping up — not only the moment pytest prints a green dot.

You already saw **verification** vs **validation**, and **static** vs **dynamic**, in [Core definitions](#core-definitions-learn-these-words-first). Both pairs show up in every real project:

Reading `values-aro.yaml` and catching the wrong storage class is static testing. Calling `/v1/chat/completions` on a live cluster is dynamic testing. You can verify a wrong product forever and still fail validation — that’s why both verification and validation matter.

### What you’re trying to achieve

The syllabus lists typical **test objectives**: evaluate work products; cause failures and find defects; reach required coverage; reduce the risk of inadequate quality; verify requirements (including contractual/legal ones); give stakeholders information for decisions; build confidence; validate that the thing is complete and works as expected.

In plain terms: find problems, learn how much you covered, lower the chance of a bad demo or release, and give people evidence — not vibes — about quality.

In this repo that looks like:

- Find defects → invalid API key must not reach the model.
- Build confidence → LLMIS is Ready and chat returns HTTP 200.
- Inform a decision → smoke failed on `ai_gateway`, so don’t demo DevSpaces yet.
- Coverage → unit cases for JSON usage, SSE with usage, SSE without usage, and garbage input.

### Testing is not debugging

**Testing** shows that something is wrong (or still looks fine). **Debugging** finds the cause and removes the defect. The syllabus keeps them separate on purpose.

After a fix you usually do two follow-ups:

1. **Confirmation testing** — the original failure is gone (re-run the test that failed).
2. **Regression testing** — the fix didn’t break neighboring behavior.

If gateway auth was broken, confirmation is “invalid key still gets 401/403.” Regression is “valid key still gets 200” and the rest of `COMPONENT=vllm` still passes.

```python
# Confirmation: the bug we fixed
assert status in (401, 403)  # missing / invalid API key

# Regression: the happy path still works
assert status == 200
assert choices  # non-empty assistant content
```

**When to use this distinction:** every time you fix something. Don’t only poke the broken path; keep a small safety net around it.

## Why bother testing?

Untested software fails in expensive ways — lost time, bad demos, broken trust. The syllabus frames testing as **quality control**: within scope, time, and budget, it helps you meet agreed quality goals. It finds defects relatively cheaply, measures quality at different moments in the lifecycle, and stands in (imperfectly) for real users when you can’t put them on every PR.

### Testing vs quality assurance (QA)

People say “QA” when they mean “testing.” The syllabus separates them:

- **Testing** is product-oriented and corrective: activities that support reaching enough quality. It’s a major form of quality *control*.
- **QA** is process-oriented and preventive: improve *how* you work so good products are more likely.

Here, conventions like “always deploy through make / GitOps” and “smoke after sync” are QA-flavored process. The pytest files are testing.

### Errors, defects, failures, root causes (same chain, in story form)

If the formal definitions above felt dense, remember only this story:

Someone is rushed and sets the wrong cloud overlay (**error**). The rendered chart has no usable gateway auth (**defect**). A demo user calls chat and gets through without a key, or the IDE cannot talk to the model (**failure**). Digging further, the team never checked the Kuadrant CRD prerequisite on existing OpenShift (**root cause**). Fixing only the symptom (one values tweak) without fixing the prerequisite check invites the same failure next cluster.

Full definitions: [Core definitions](#core-definitions-learn-these-words-first).

## Seven principles (keep these)

These are general guidelines the syllabus treats as foundations:

1. **Testing shows the presence of defects, not their absence.** Green smoke lowers risk; it never proves “zero bugs.”
2. **Exhaustive testing is impossible.** You can’t try every prompt, key, and cluster state. You choose with techniques and risk.
3. **Early testing saves time and money.** A bad Python parse caught by `make unit` is cheaper than debugging Langfuse on a GPU node.
4. **Defects cluster.** A few areas (gateway auth, model runtime flags, Helm naming limits) produce most pain — test those harder.
5. **Tests wear out.** Repeating the exact same checks forever finds fewer *new* bugs. Update tests when the product changes. (Automated regression is still valuable; the warning is against stale, never-growing suites.)
6. **Testing is context dependent.** Avionics ≠ a private coding assistant. Our bar is closer to “deploy works, auth works, model answers.”
7. **Absence-of-defects fallacy.** Verifying every written requirement can still leave you with a product nobody can use. Validate too — e.g. a real DevSpaces chat through `maas-default-gateway`.

## The work of testing (activities), without the bureaucracy

Even when a team is small, the syllabus’s activity groups are a useful mental loop:

**Plan** → **monitor/control** → **analyze** (“what to test?”) → **design** (“how to test?”) → **implement** → **execute** → **complete**.

On this project that might be: after a chart change, plan to run smoke; analyze that API keys are high risk; design missing/invalid/valid key cases; implement them in `test_ai_gateway.py`; execute with `make smoke COMPONENT=ai_gateway DEV_USER=dev-user1`; then note skips or file a fix.

The artifacts you produce — scripts, fixtures, logs, bug notes — are **testware**. Traceability (connecting a requirement or risk to a test) helps you answer “did we cover auth?” without guessing.

Roles in the syllabus split *test management* from *testing engineering*. Here one person often wears both hats: choose scope (`COMPONENT=…`) and write/run the checks.

**Independence** helps: authors miss their own assumptions. A second person running smoke on a fresh namespace, or a careful PR review, is a lightweight form of that idea.

---

# Chapter 2 — Testing through the lifecycle

Testing isn’t a phase glued on at the end. It changes shape as the product grows.

## Shift left, DevOps, and “tests first”

**Shift left** means do testing earlier — without abandoning later testing. Write unit checks while you write the parser; don’t wait for a full cluster to discover empty/malformed handling is wrong. You still need smoke later, because OpenShift reality isn’t a unit test.

**DevOps**, in the syllabus’s sense, is about development (including testing) and operations working toward shared goals: fast feedback, CI/CD, automation, less painful release. This repo leans on GitOps for deploy and on `make smoke` for “is the running system okay?” Smoke is developer-run against a live cluster by design — still the same spirit: verify the real thing after sync.

Three related “tests drive design” approaches:

- **TDD** — write a small test first, then code until it passes, then refactor.
- **ATDD** — derive tests from acceptance criteria before building the feature.
- **BDD** — describe behavior in readable examples (often Given / When / Then) that can become automated checks.

You don’t need religion about them. Use the spirit: clarify “done” before you bury yourself in YAML.

```python
# TDD-style: this failing test defines done for usage parsing
def test_usage_from_non_stream_json(mod):
    body = json.dumps({
        "choices": [{"message": {"content": "hi"}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }).encode()
    assert mod._usage_from_response(body) == {
        "input": 10, "output": 5, "total": 15,
    }
```

```text
ATDD / acceptance story for the gateway:

As a DevSpaces user,
I want chat/completions to require my per-namespace API key,
so that other namespaces cannot use my access.

Given no Authorization header
When I POST /v1/chat/completions
Then the status is 401 or 403
```

**When to use:** TDD for pure logic you own; ATDD/BDD when several people must agree on behavior (auth, IDE routing); shift-left unit tests always for parsers and helpers; smoke after every meaningful deploy.

## Test levels — how “big” is the thing under test?

A **test level** is a group of test activities organized and managed together for software at a given stage — from a single component up to a system of systems.

The syllabus names five levels. Below: what each means, when to use it, and an example tied to this repo (or a small “if we added it” case when we don’t have that level yet).

| Level | What it means | Here |
|-------|----------------|------|
| **Component (unit)** | One piece in isolation, often with a unit framework | `tests/unit/` → `make unit` |
| **Component integration** | Interfaces between pieces | thin today — see example below |
| **System** | Overall behavior of the product | core of `make smoke` (`readiness`, `vllm`, …) |
| **System integration** | Our system talking to other systems/services | smoke markers like `ai_gateway`, `grafana`, `langfuse` |
| **Acceptance** | Validation / ready for users or ops | `make uat` (OpenCode coding task) + manual DevSpaces UAT |

**Smoke** is an industry name for a thin post-deploy “is it on fire?” suite. ISTQB does **not** list it as a sixth test level. In this guide it sits under **system testing**, with some markers that are really **system integration** (details below).

### 1) Component testing (unit testing)

**Meaning:** Test one component in isolation. Usually run by developers in a local environment, with a unit framework (here: pytest). No real cluster required.

**Use this level when:**

- You changed (or are writing) a pure function / parser / helper (e.g. `_usage_from_response`)
- You want feedback in seconds on a laptop — before any Helm deploy
- The bug can be reproduced with fake inputs (JSON bytes, SSE strings) — no live model needed
- You’re doing TDD on logic you own
- You need many cases cheaply (EP, BVA, branch coverage)

**Do not use this level alone when:**

- The question is “is the cluster / gateway / model actually up?”
- You need real AuthPolicy, Secrets, or OpenShift Ready conditions
- You’re validating a developer workflow in DevSpaces / OpenCode

**In this repo:** run `make unit` on every change under `charts/.../files/*.py` (and any shared helpers).

**Example in this repo** — `tests/unit/test_pca_langfuse_io.py` exercises only `_usage_from_response` from `pca_langfuse_io.py`:

```python
# make unit — no OpenShift, no model, no network
def test_usage_from_non_stream_json(mod):
    body = json.dumps({
        "choices": [{"message": {"content": "hi"}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }).encode()
    assert mod._usage_from_response(body) == {
        "input": 10, "output": 5, "total": 15,
    }

def test_usage_from_empty_and_malformed(mod):
    assert mod._usage_from_response(b"") is None
    assert mod._usage_from_response(b"not-json") is None
```

### 2) Component integration testing

**Meaning:** Test the *interfaces and interactions between* components (not the whole product). Strategy can be bottom-up, top-down, or “big bang.”

**Use this level when:**

- Two or more of *your* modules must cooperate (middleware wraps an app; helper A calls helper B with real wiring)
- Unit tests of each piece are green, but you’re unsure about the contract between them (headers, body streaming, error propagation)
- You can still fake the outside world (fake ASGI app, fake HTTP client) — no full OpenShift
- You changed how pieces are composed (e.g. “middleware now reads the response after streaming”)

**Do not use this level when:**

- A single function’s logic is enough — stay at unit
- You need Gateway CRs, Kuadrant, or a real vLLM — that’s system / system integration
- You’re asking “can a user finish a coding task?” — that’s acceptance

**In this repo:** thin today. Add this when middleware ↔ server wiring gets risky; don’t replace smoke with it.

**Example (aspirational for this repo)** — wire `langfuse_io_middleware` to a tiny fake ASGI app and check the request/response boundary (still local pytest):

```python
# Not in the repo yet — pattern for component integration
async def test_middleware_passes_through_and_sees_response_body():
    async def fake_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({
            "type": "http.response.body",
            "body": b'{"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}',
        })

    app = langfuse_io_middleware(fake_app)
    # call app with a fake /v1/chat/completions request…
    # assert client still gets 200 AND middleware could parse usage from the body
```

That checks the *handshake between pieces*, not “is OpenShift Ready?”

### 3) System testing

**Meaning:** Test the overall behavior and capabilities of the *entire system* — end-to-end functional paths and often non-functional checks — usually against specifications for that system.

**Use this level when:**

- You just deployed or synced AI serving (`make ai-serving-deploy-existing-openshift`, ArgoCD sync, chart bump)
- You need to know the product as a whole is healthy: LLMIS Ready, PVC Bound, pods running, `/v1/models` / chat / stream / tools work
- You’re doing a quick “is it on fire?” pass before a demo (`make smoke`, or `COMPONENT=readiness` then `vllm`)
- You changed model image, vLLM args, hardware profile, or storage — and need the full serving path checked
- You’re doing maintenance testing after a hotfix on the live stack

**Do not use this level when:**

- Only a pure Python helper changed and you haven’t deployed — start with `make unit`
- You specifically need to prove *cross-product* auth/telemetry contracts — add system integration focus (`ai_gateway`, `grafana`, `langfuse`)
- You need proof a human/IDE workflow succeeds — use acceptance / `make uat`

**In this repo:** `make smoke` (especially `readiness` + `vllm`) is your main system net.

**Example in this repo** — readiness + vLLM smoke (`make smoke` / `COMPONENT=readiness` or `vllm`):

```python
# System: the deployed product must be Ready and answer OpenAI-compatible APIs
def test_llminferenceservice_ready(ai_namespace: str, oc_user: str) -> None:
    status = oc.condition_status(
        "llminferenceservice", urls.LLMIS_NAME, "Ready", ai_namespace
    )
    assert status == "True"

def test_chat_completions(ai_namespace: str, gateway_v1: str, model_id: str) -> None:
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{gateway_v1}/chat/completions",
        method="POST",
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": "Say hello in one word."}],
            "stream": False,
            "max_tokens": 32,
        },
        timeout_secs=180,
    )
    assert status == 200
    assert oc.message_text((body.get("choices") or [])[0]).strip()
```

#### Smoke testing (under system — sometimes system integration)

**Smoke testing** is an industry term (not one of ISTQB’s five formal test levels). Meaning: after a build or deploy, run a **small, critical** set of checks to see if the system is basically alive. If smoke fails, stop — don’t bother with deep regression or a demo yet.

**Where it belongs in ISTQB terms**

| Smoke slice in this repo | ISTQB category | Why |
|--------------------------|----------------|-----|
| `COMPONENT=readiness` | **System** | Whole product objects Ready/Bound/Accepted |
| `COMPONENT=vllm` | **System** | End-to-end serving behavior of the AI product |
| `COMPONENT=guardrails` (health + basic chat path) | Mostly **system** | Filter as part of the serving product |
| `COMPONENT=ai_gateway` | **System integration** | RHCL gateway ↔ llm-d/vLLM + secrets/AuthPolicy |
| `COMPONENT=grafana` / `langfuse` / `otel` | **System integration** | Our stack ↔ observability products |
| `COMPONENT=devspaces` (config + harness via gateway) | **System integration** | DevSpaces ↔ gateway/model |

So: **`make smoke` is categorized primarily as system testing**; some markers also cover system integration. It is **not** component/unit, and it is **not** acceptance (`make uat` / manual UAT is).

**Use smoke when:**

- You just deployed or synced charts and need a fast go/no-go
- You want a thin net before a demo or before running UAT / e2e
- You’re doing maintenance testing after a config/image change

**Do not treat smoke as:**

- Full functional coverage of every feature
- Model-quality / eval testing (“was the answer good?”)
- A substitute for unit tests on pure logic
- Proof of user acceptance (use acceptance / `make uat`)

**In this repo**

```bash
make smoke                              # full thin suite
make smoke COMPONENT=readiness          # system: objects Ready?
make smoke COMPONENT=vllm               # system: model APIs work?
make smoke COMPONENT=ai_gateway DEV_USER=dev-user1   # system integration: front door
```

Package: `tests/cluster-smoke/` (see its README). Optional components auto-skip when absent.

### 4) System integration testing

**Meaning:** Test interfaces between *this* system and *other* systems or external services. Needs an environment close to real operations.

**Use this level when:**

- You changed how two products meet: RHCL AI gateway ↔ llm-d/vLLM, Grafana ↔ Prometheus, Langfuse ↔ chat traffic, DevSpaces config ↔ gateway host/API key
- Each side might be “up,” but the handshake can still be wrong (401/403, wrong datasource path, missing mirror Secret)
- You enabled or reconfigured `aiGateway`, AuthPolicy, API keys, or observability
- A past incident was at a boundary (Thanos proxy 400, Langfuse short names, missing `pca-maas-apikey`)

**Do not use this level when:**

- You’re only checking one internal function — unit is enough
- You only need “LLMIS Ready + bare chat on llm-d” with no front-door/other product — system/`vllm` may be enough
- You need “developer finished a real coding task in the IDE” — acceptance / `make uat`

**In this repo:** `make smoke COMPONENT=ai_gateway DEV_USER=dev-user1`, plus `grafana` / `langfuse` / `otel` / `devspaces` markers as needed.

**Example in this repo** — AI gateway (RHCL) in front of llm-d/vLLM, and Grafana talking to Prometheus:

```python
# System integration: RHCL gateway + AuthPolicy + upstream inference
def test_chat_completions_with_valid_api_key(
    ai_namespace, ai_gateway_v1, model_id, require_dev_namespace
):
    api_key = oc.secret_data(
        urls.AI_GATEWAY_APIKEY_SECRET,
        urls.AI_GATEWAY_APIKEY_KEY,
        require_dev_namespace,
    )
    status, body = oc.in_cluster_http(
        ai_namespace,
        f"{ai_gateway_v1}/chat/completions",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}"},
        json_body={
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with the single word pong."}],
            "stream": False,
            "max_tokens": 32,
        },
        timeout_secs=180,
    )
    assert status == 200
    assert (body.get("choices") or [])

# Another system-integration slice: Grafana → Prometheus datasource
# (see tests/cluster-smoke/test_grafana.py — /api/ds/query must work)
```

Here the test object is the *path across systems* (gateway auth service + inference stack), not a single Python function.

### 5) Acceptance testing

**Meaning:** Focus on **validation** and readiness for deployment — does the system meet the user’s business needs? Ideally done by intended users. Forms include UAT, operational acceptance, contractual/regulatory, alpha/beta.

**Use this level when:**

- You’re about to demo or hand the stack to developers and need “they can actually work,” not only “APIs return 200”
- You changed DevSpaces / OpenCode / IDE extension wiring and need a real user-path check
- Smoke is green, but you still need confidence in the full IDE → gateway → model → useful outcome loop
- Stakeholders ask “is this acceptable for our use case?” (validation, not only verification)
- You’re signing off a release / workshop environment (UAT-style pass)

**Do not use this level when:**

- You’re iterating on a parser — too slow; use unit first
- You only need a post-deploy health net — start with `make smoke`
- You don’t have a DevSpaces user / OpenCode workspace yet — fix deploy first, then accept

**In this repo:** `make uat DEV_USER=dev-user1` for automated UAT; plus a short manual DevSpaces session. `make e2e` stays the OpenCode/MaaS front-door net (routes, streaming, guardrails), not the coding-task proof.

**Example in this repo** — OpenCode UAT: the IDE agent clones a calculator, adds `power`, and unittest proves `power(2, 4) == 16`. That is closer to “a developer can get real work done” than “HTTP 200 from `/v1/models`.”

```bash
make uat DEV_USER=dev-user1
# tests/uat/test_developer_coding_task.py
```

Manual acceptance still matters too: log into DevSpaces as `dev-user1`, open Continue/Roo/Cline/OpenCode, and complete a short coding task through `maas-default-gateway`.

### Which level in which case? (cheat sheet)

| Case / situation | Use this level | Command / action |
|------------------|----------------|------------------|
| Changed Python helper / parser under `charts/.../files` | Component (unit) | `make unit` |
| Writing logic first (TDD), many edge cases | Component (unit) | `make unit` |
| Middleware must wrap an app correctly (local) | Component integration | local pytest with fakes (add when needed) |
| Just deployed / synced AI serving | System | `make smoke` or `COMPONENT=readiness,vllm` |
| Changed model image, vLLM flags, PVC/hardware | System | `make smoke COMPONENT=vllm` (+ readiness) |
| “Is the stack on fire before the demo?” | System | `make smoke` |
| Changed RHCL gateway, AuthPolicy, API keys | System integration | `make smoke COMPONENT=ai_gateway DEV_USER=…` |
| Changed Grafana/Langfuse/OTel wiring | System integration | `COMPONENT=grafana` / `langfuse` / `otel` |
| DevSpaces config must point at gateway + key | System integration | `COMPONENT=devspaces` / `ai_gateway` |
| Need proof a developer can finish real work in IDE | Acceptance | `make uat DEV_USER=…` + manual UAT |
| Workshop / release sign-off | Acceptance | UAT + manual DevSpaces checklist |
| Fixed a bug at any level | Same level (confirmation) + nearby higher/lower regression | re-run the failing test + smoke/unit as fits |

**Rule of thumb for this repo:** unit while coding → smoke after deploy → gateway/observability markers when boundaries change → `make uat` before you claim “developers can use it.”

### Why not only acceptance testing? Why unit and integration too?

**Question:** If acceptance testing proves the real user goal (e.g. OpenCode can add `power` to a calculator), why bother with unit and integration tests at all?

**Answer:** Acceptance testing alone is **too late, too slow, and too blunt** to be your only net.

If you only do acceptance:

- A tiny parser bug still forces a full deploy + IDE run to find it
- Failures are hard to localize (“UAT failed” — was it auth, model, IDE, prompt, network?)
- You can’t cover many edge cases cheaply (empty JSON, bad SSE, weird boundaries)
- Feedback takes minutes/hours, so you fix less and guess more
- Flaky infra (GPU, cluster, IDE) makes green/red noisy
- Green acceptance still won’t prove all internal contracts; it only proves one user path

That’s why the other levels exist:

- **Unit** — fast, precise, many cases. “This function is wrong” in seconds.
- **Component / system integration** — prove pieces (or systems) connect correctly, before/without a full user journey.
- **Acceptance** — prove the product is actually usable for the real goal.

Think of it like building a car: unit measures each part; integration checks the engine attaches to the gearbox; acceptance is driving the car. You wouldn’t only test by driving, and you wouldn’t only measure bolts and never drive.

**In this repo:** `make unit` catches Langfuse parsing bugs without a cluster; `make smoke` catches deploy/auth/model issues; `make uat` proves a developer workflow. Skip the lower levels and every small mistake becomes an expensive UAT mystery.

(This is also why the [test pyramid](#the-test-pyramid) wants many fast narrow tests at the base and fewer slow broad ones at the top.)

## Test types — what kind of quality are you checking?

A **test type** groups activities around a quality concern. The same type can appear at many levels.

**Functional testing** asks what the system should do — completeness, correctness, appropriateness of functions. Example: `/v1/models` lists the configured model; chat returns choices; tool-calling returns structured `tool_calls` (with `enable_thinking: false` for Qwen).

**Non-functional testing** asks how well the system behaves. The syllabus points at ISO/IEC 25010 themes such as performance efficiency, compatibility, usability, reliability, security, maintainability, portability/flexibility, and safety. In this repo: API-key security on the gateway; Ready/Accepted as reliability signals; GuideLLM benchmarks when you care about load (opt-in chart, not everyday).

**Black-box testing** derives tests from specified behavior without using internal structure. You treat the AI gateway as a sealed HTTP service: missing key → 401/403.

**White-box testing** derives tests from internal structure (code, architecture, flows). You open `_usage_from_response` and make sure both SSE and non-SSE paths run.

**When to use:** functional checks for every user-facing path you claim works; security/reliability non-functionals early for the gateway; black-box at HTTP boundaries; white-box for parsers and branching helpers. Don’t use GuideLLM to prove auth — wrong tool for the job.

## Confirmation, regression, and maintenance

You already met confirmation and regression. They apply at **every** level when you fix or change something.

**Maintenance testing** is testing changes to a system that’s already operational: did the change work, and did the rest stay healthy? Triggers include planned enhancements, hotfixes, environment upgrades/migrations, and retirement/archiving.

Redeploying `pca-ai-serving` with a new model image and running `make smoke` (or at least `readiness` + `vllm` + `ai_gateway`) *is* maintenance testing.

**When to use:** any time the cluster already exists and you’re changing charts, images, or config. Scope the retest to risk: small values tweak → focused markers; scary gateway change → full smoke.

---

# Chapter 3 — Static testing

## Looking without running

**Static testing** examines work products without executing them — reviews and static analysis. **Dynamic testing** executes the test object.

Why care? Defects found here never become cluster failures. Ambiguous values, missing prerequisites, and “this Helm name will be too long for Bitnami labels” show up in reading long before Langfuse CrashLoops.

| Work product | Static habit here |
|--------------|-------------------|
| Helm values / templates | PR review; sanity-check cloud overlays |
| Python under `charts/.../files` | read + linters + later unit tests |
| Deploy docs / `AGENTS.md` | catch wrong namespaces before a demo |
| AuthPolicy / Gateway YAML | review shape before sync |

Static testing finds **defects** in the artifact. Dynamic testing may show **failures** when something runs. Different lens, same goal: quality information.

## Feedback and reviews (practical, not ceremonial)

The syllabus describes review processes, roles, and types (informal review, walkthrough, technical review, inspection). On this project the useful form is usually: early PR feedback, reading charts with a short checklist, and fixing ambiguity before Argo syncs.

A lightweight checklist (this is already “checklist-based” thinking from chapter 4):

```text
[ ] Storage class / GPU product match ARO vs ROSA (or existing OCP)
[ ] aiGateway: create Kuadrant vs reuse on a shared cluster
[ ] model.id / model.name match what smoke will look for
[ ] No secrets committed
[ ] New skip/optional behavior documented in tests/cluster-smoke/README.md
```

**When to use static testing:** every PR that touches charts or middleware; before expensive cluster experiments; whenever requirements or docs feel fuzzy. Use dynamic tests to prove the running system; don’t skip reading just because smoke exists.

---

# Chapter 4 — Choosing what to test (analysis & design)

This chapter is where testing stops being “write a random assert” and becomes a craft. **Test techniques** help you build a relatively small but sufficient set of cases. The syllabus groups them into black-box, white-box, and experience-based — plus collaboration approaches that prevent defects by agreeing early.

## Black-box techniques

These start from specified behavior, not from reading the implementation. If the implementation changes but required behavior stays the same, the tests often still apply.

### Equivalence partitioning

**Equivalence partitioning (EP)** divides data into partitions you expect the system to treat the same way. The idea: if one value from a partition finds a defect, other values from that partition likely would too — so one representative per partition is enough for that technique. Partitions shouldn’t overlap; they can be valid or invalid depending on whether the system should accept or reject them.

**When to use:** inputs fall into clear “kinds” (auth present/absent, body shapes, optional components installed or not).

**Example — gateway Authorization** (see `test_ai_gateway.py`):

| Partition | Example | Expect |
|-----------|---------|--------|
| Missing auth | no header | 401/403 |
| Invalid key | `Bearer invalid-smoke-test-key` | 401/403 |
| Valid key | secret `pca-maas-apikey` | 200 + content |

You don’t need a hundred random strings. You need each *kind*.

**Example — usage body shapes** (already in `tests/unit/test_pca_langfuse_io.py`): non-stream JSON with usage; SSE with a final usage chunk; SSE without usage; empty/malformed → `None`.

### Boundary value analysis

**Boundary value analysis (BVA)** exercises the edges of *ordered* partitions — mins and maxes — because off-by-one mistakes cluster there. The syllabus describes **2-value** BVA (boundary + neighbor in the adjacent partition) and stricter **3-value** BVA (boundary + both neighbors).

**When to use:** numbers, lengths, timeouts, quotas — anything with a clear ordered range. Less useful for unordered categories (those are EP).

**Example — if `max_tokens` must be 1..4096:**

```python
@pytest.mark.parametrize(
    "max_tokens,ok",
    [(0, False), (1, True), (2, True), (4096, True), (4097, False)],
)
def test_max_tokens_boundaries(max_tokens, ok):
    assert (1 <= max_tokens <= 4096) is ok
```

Smoke often uses small `max_tokens` for speed. That’s fine for “pipe works”; use BVA when *you* own the validation rules.

### Decision tables

When several conditions combine into different outcomes, a **decision table** records rules as columns: conditions and resulting actions. You aim to cover feasible columns so combinations aren’t forgotten. Tables also expose gaps and contradictions in requirements.

**When to use:** business rules, feature flags, “enabled only if A and B and C.”

**Example — Langfuse emit enabled?** roughly: capture mode is `full`, and both keys are set.

| CAPTURE=full | public key | secret key | Emit? |
|:------------:|:----------:|:----------:|:-----:|
| T | T | T | Yes |
| T | T | F | No |
| T | F | T | No |
| F | T | T | No |

Turn each row into a test (or parametrize rows). That’s decision-table testing in pytest clothing.

### State transition testing

Some behavior is about **states** and **transitions** (event, optional guard, action). You can cover all states, all valid transitions, or even attempt invalid transitions (important in safety-critical contexts).

**When to use:** lifecycles — PVC Pending→Bound, Gateway Accepted, LLMIS Ready, DevWorkspace phases.

Smoke usually asserts the *desired* end state (`Bound`, `Ready`, `Accepted`). That’s a practical slice of state testing. Full “try illegal transitions” is often too destructive for shared demo clusters — save it for staging experiments.

```python
def test_model_cache_pvc_bound(ai_namespace: str) -> None:
    assert oc.pvc_phase(urls.PVC_NAME, ai_namespace) == "Bound"
```

## White-box techniques

These use the internal structure. The syllabus focuses on code **statement** and **branch** testing.

- **Statement coverage** — fraction of executable statements exercised. 100% means every executable statement ran at least once; it still won’t catch every data-dependent bug, and it may miss some logic paths.
- **Branch coverage** — fraction of branches (transfers of control) exercised. 100% branch coverage **subsumes** statement coverage: it implies statement coverage, not the other way around.

**When to use:** pure functions with real branching — parsers, middleware helpers, URL builders. Pair with black-box at the HTTP edge so you don’t only test the code you happened to write.

The Langfuse usage tests are a white-box-minded set: they exist specifically to hit SSE vs non-SSE vs empty paths inside `_usage_from_response`.

## Experience-based techniques

When specs are thin or the product has scars, experience matters.

**Error guessing** anticipates errors, defects, and failures from how the app failed before, what developers usually get wrong, and failures in similar systems. **Fault attacks** turn that into an explicit list you try to trigger.

This repo’s smoke README table is error guessing written down: Qwen thinking mode vs tool calls; Grafana/Thanos proxy 400s; Helm release names that break Bitnami labels.

**Exploratory testing** designs, executes, and evaluates *while* you learn. Often you time-box a session with a **charter** (goal), then debrief. It complements scripted tests; it doesn’t replace them when you need repeatability.

```text
Charter (45–90 min):
Can a new DevSpaces user reach the model only through maas-default-gateway?
Try wrong keys, Continue/Roo host config, OpenCode env, missing DEV_USER…
```

**Checklist-based testing** runs against a concrete list of conditions — not vague vibes, not things already fully automated elsewhere. Update the list when new high-severity defects appear; don’t let it grow into a novel.

Smoke markers (`readiness`, `vllm`, `ai_gateway`, …) are a checklist you can run with `COMPONENT=`.

**When to use experience-based techniques:** after incidents, during unfamiliar chart changes, when automating everything would be premature, or when you need human curiosity on top of green CI.

## Collaboration: stories, acceptance criteria, ATDD

Black/white/experience techniques hunt defects. Collaboration approaches also **prevent** them by aligning business, development, and testing early.

A **user story** is often framed with the “3 C’s”: Card, Conversation, Confirmation (acceptance criteria). Good stories are INVEST: Independent, Negotiable, Valuable, Estimable, Small, Testable.

**Acceptance criteria** are conditions the implementation must meet to be accepted — effectively test conditions. They define scope, force consensus, and describe positive and negative scenarios.

**ATDD** creates those tests (examples) before or as you implement, often in a workshop, covering happy path, then negative cases, then important non-functionals.

**When to use:** any feature that crosses teams or charts (gateway + DevSpaces + secrets). If you can’t phrase acceptance criteria, you don’t know “done” yet — don’t only code.

---

# Chapter 5 — Managing testing without drowning in process

You still need a little management thinking even on a small project. Here’s the useful core.

## Plan enough to decide scope

A **test plan** answers what you’ll test, how, with what entry/exit ideas, and what you’ll skip. It doesn’t need a 20-page template.

**Entry criteria** — are we allowed to start? Example for smoke: `oc whoami` works; AI serving is deployed; for gateway tests, `DEV_USER` is set.

**Exit criteria** — are we done enough? Critical markers green, or failures understood and tracked; optional components skipped only when truly absent.

**Prioritize.** Not every test is equal. A sensible order here: readiness → vllm → ai_gateway → optional observability/guardrails/DevSpaces.

### The test pyramid

The syllabus discusses the **test pyramid**: many fast, narrow tests at the base; fewer slow, broad tests at the top.

```text
        /  manual acceptance / demo  \     few
       /   cluster smoke (make smoke) \    some
      /     unit tests (make unit)      \   many (goal)
```

Honest status: this repo is still a bit **top-heavy** (rich smoke, few units). That’s common in platform work, but it’s slower and flakier. Prefer growing unit tests for pure logic; keep smoke as a thin net over the real cluster.

## Risk-based testing

**Risk** combines how likely something is to go wrong with how bad that would be. **Risk-based testing** spends more effort where risk is high.

| Risk | Why it hurts | What we do |
|------|--------------|------------|
| Open / weak gateway auth | Anyone could hit the model | `ai_gateway` auth tests |
| Model not Ready | Nothing works | readiness + vllm |
| Langfuse naming limits | Known past outage mode | langfuse service checks |
| Wrong Grafana query path | Blind ops | grafana `/api/ds/query` |

**When to use:** always, even informally. If time is short, cut low-risk checks first — not auth and readiness.

## Monitoring, config, defects (short)

**Monitoring/control** means noticing progress and steering: failures, skips, flakes. Skipping Langfuse tests when the route is absent is adapting to context — good — as long as you don’t confuse “skipped” with “proven installed.”

**Configuration management** means knowing which code, tests, and deployed versions belong together. The `model_id` fixture reading the live LLMIS is a small example of aligning tests with the actual cluster.

**Defect reports** that help: command you ran, namespace, expected vs actual, snippet of evidence (`oc describe`, status code, body), and how bad it is for the demo.

---

# Chapter 6 — Tools (keep perspective)

Tools support testing; they don’t replace thinking. The syllabus stresses both benefits of automation (speed, repeatability, broader regression) and risks (cost to maintain, brittle suites, false confidence).

What we actually use:

| Tool | Role |
|------|------|
| pytest + fixtures/markers | structure and selection |
| pytest-xdist (`N_PARALLEL`) | faster smoke |
| `make unit` / `make smoke` | stable entry points |
| `oc` (+ in-cluster curl pods) | cluster truth |
| linters / PR review | static aid |
| GuideLLM (optional) | load/perf-style probing |

**When to automate:** stable, high-value, repeatable checks — Ready conditions, auth, `/v1/models`, parsing helpers.  
**When not to over-automate:** fuzzy model quality (“was that coding answer good?”), one-off cluster archaeology, and exploratory learning sessions.

---

# Appendix A — What ISTQB doesn’t name (this AI stack)

Foundation-level ISTQB won’t walk you through LLMs. A few distinctions save confusion:

**Serving correctness vs model quality.** Smoke proves the pipe: model loaded, API answers, auth holds, streaming emits `data:` lines, tools return structure. It does *not* prove answers are accurate, safe, or useful. Asserting “non-empty content” ≠ eval.

**What to automate vs judge.** Automate infrastructure and contract checks. Keep human or dedicated eval harnesses for accuracy, nuanced safety, and “does this help a developer?” Guardrails smoke (`/healthz`, clean chat, injection block) is a start for filter behavior — not a full security audit.

**Observability tests** (Grafana, Langfuse, OTel) ask whether you can *see* the system. That’s operability; still not model eval — though “trace appears after chat” proves the telemetry path.

**Growth path that fits the syllabus mindset:** more unit tests for pure Python; keep smoke thin; if you need quality gates for the LLM, add a separate eval path with datasets and scoring — don’t overload smoke with `assert "pong" in text` folklore.

---

# Appendix B — Pocket guide: what should I reach for?

| You’re in this situation | Reach for |
|--------------------------|-----------|
| Changed a parser or helper | Unit tests; EP + branch coverage |
| Changed gateway auth / IDE keys | Smoke `ai_gateway`; decision table for auth combos |
| Changed model image or vLLM args | Smoke `readiness` + `vllm`; short exploratory IDE session |
| Fixed a bug | Confirmation of the failing test + nearby regression |
| Optional component may be missing | Skip with a clear reason (context-dependent), don’t hard-fail the universe |
| “Is it fast enough?” | Benchmarks / GuideLLM, not unit tests |
| Specs fuzzy / chart unfamiliar | Exploratory charter + write acceptance criteria |
| Values/docs/PR | Static review checklist before you burn cluster time |
| Time is almost gone | Risk order: readiness → vllm → ai_gateway |

---

# Appendix C — Full glossary (definitions + when you’ll meet them)

Start with [Core definitions](#core-definitions-learn-these-words-first) for error / defect / failure / root cause. This table is the wider vocabulary from later chapters.

| Term | Definition (syllabus-aligned) | Plain meaning | Repo cue |
|------|-------------------------------|---------------|----------|
| **Error** | Human mistake | Slip by a person | Wrong values typed |
| **Defect / fault / bug** | Flaw in a work product produced by an error | Wrong thing in code/YAML/docs | Missing AuthPolicy in chart |
| **Failure** | System misbehaves when running (often after a defect is executed) | Observable wrong behavior | Chat returns 200 without API key |
| **Root cause** | Fundamental reason a problem occurred | Deeper “why” | Kuadrant CRD never installed |
| **Testing** | Activities to find defects and evaluate quality of work products | Looking for problems + judging quality | `make unit` / `make smoke` / PR review |
| **Test object** | Work product under test | Thing you’re testing | `pca_langfuse_io.py` or the AI namespace |
| **Test basis** | Knowledge you derive tests from | Specs, risks, stories, known bugs | README “known issues”, gateway auth rules |
| **Test condition** | Testable aspect you decide to check | “What to test” item | “invalid key rejected” |
| **Test case** | Concrete check with inputs + expected results | One `test_…` (or manual steps) | `test_chat_completions_rejects_invalid_api_key` |
| **Test data** | Data needed to run tests | Keys, payloads, model id | Secret `pca-maas-apikey` |
| **Expected result** | Correct outcome if the system is right | What should happen | `status in (401, 403)` |
| **Actual result** | Outcome you observed | What did happen | `status == 200` |
| **Anomaly** | Observation that differs from expectations | “That’s not right…” | Failed assert / odd review finding |
| **Coverage** | How much of a defined set was exercised | How thoroughly you poked X | All auth partitions; SSE + JSON branches |
| **Verification** | Meets specified requirements | Built as specified? | Auth rules match design |
| **Validation** | Meets stakeholder needs in real use | Right product? | DevSpaces chat is usable |
| **Static testing** | Examine without executing | Read/analyze | Review Helm values |
| **Dynamic testing** | Examine by executing | Run it | pytest against cluster/API |
| **Debugging** | Find and remove defects causing failures | Fix the bug | Reproduce → diagnose → patch |
| **Quality assurance (QA)** | Process-oriented prevention / process improvement | Improve how we work | Make targets, GitOps conventions |
| **Quality control** | Product-oriented checks (testing is a major form) | Check this product | Smoke after deploy |
| **Testware** | Artifacts created for testing | Tests, fixtures, logs, reports | `tests/cluster-smoke/` |
| **Traceability** | Links between basis, tests, results, defects | “This risk → these tests” | Marker `ai_gateway` ↔ auth requirements |
| **Test level** | Activities grouped by development “height” | How big a piece | Unit vs system smoke |
| **Component (unit) testing** | Test a component in isolation | One piece alone | `tests/unit/` |
| **System testing** | Overall behavior of a whole system | Whole product path | Most of `make smoke` |
| **Acceptance testing** | Validation / readiness for users or ops | Good enough to accept | `make uat` + manual DevSpaces UAT |
| **Test type** | Activities grouped by quality characteristic | What kind of quality | Functional vs security |
| **Functional testing** | Checks what the system should do | Correct features | `/v1/models`, chat choices |
| **Non-functional testing** | Checks how well it behaves | Speed, security, reliability… | API-key security; Ready conditions |
| **Black-box testing** | From specified behavior, not internals | Outside-in | HTTP status on gateway |
| **White-box testing** | From internal structure | Inside-out | Branch coverage of usage parser |
| **Confirmation testing** | Shows an original defect was fixed | Bug gone? | Re-run the failing auth test |
| **Regression testing** | Shows a change caused no adverse effects elsewhere | Anything else broken? | Rest of `COMPONENT=vllm` |
| **Maintenance testing** | Testing changes to an operational system | Retest after change in prod-like env | Redeploy chart → smoke |
| **Shift left** | Test earlier in the lifecycle | Don’t wait until the end | `make unit` before cluster |
| **Equivalence partitioning** | One representative per class of inputs treated the same | Group similar inputs | Missing / invalid / valid API key |
| **Boundary value analysis** | Exercise edges of ordered partitions | Test the edges | `max_tokens` 0,1,4096,4097 |
| **Decision table testing** | Cover combinations of conditions → actions | Table of rule combos | Langfuse emit only if keys+flag |
| **State transition testing** | Cover states / transitions | Mode changes | PVC Bound, LLMIS Ready |
| **Statement coverage** | % of executable statements run | Did each line run? | Parser lines executed |
| **Branch coverage** | % of branches run | Did each if/else path run? | SSE vs non-SSE paths |
| **Error guessing** | Design tests from anticipated faults | Poke known scar tissue | Qwen `enable_thinking: false` case |
| **Exploratory testing** | Design+execute+learn together in a session | Structured wandering | Time-boxed DevSpaces charter |
| **Checklist-based testing** | Cover items on a concrete checklist | Don’t-forget list | Smoke component markers |
| **Acceptance criteria** | Conditions a story must meet to be accepted | Definition of done for a story | “no key → 401/403” |
| **Entry criteria** | Conditions to *start* testing | Are we allowed to begin? | `oc whoami` + deploy present |
| **Exit criteria** | Conditions to *stop* / finish testing | Are we done enough? | Critical markers green |
| **Product risk** | Risk of a bad product quality attribute | What could be wrong in the product | Open gateway |
| **Project risk** | Risk to project success (schedule, resources…) | What could sink the project | No GPU nodes, blocked sync |
| **Risk-based testing** | Focus effort using risk level (likelihood × impact) | Test scary things first | readiness → vllm → ai_gateway |
| **Test pyramid** | Many narrow/fast tests, fewer broad/slow ones | Shape of the suite | Grow `tests/unit`; keep smoke thin |
| **Test automation** | Using tools to execute/compare/report tests | Machines run the checks | pytest + `make smoke` |
| **Smoke (industry term)** | Thin post-deploy suite; **not** an ISTQB test level — categorized under **system** (some markers = **system integration**) | “Is it on fire?” | `make smoke` → see [Smoke testing](#smoke-testing-under-system--sometimes-system-integration) |

---

## A simple way to learn this with the repo

1. Run `make unit` and read `tests/unit/test_pca_langfuse_io.py` while chapter 4 (EP + branches) is fresh.
2. Read `tests/cluster-smoke/README.md`, then `test_ai_gateway.py` and `test_vllm.py`.
3. Skim the seven principles and the risk/pyramid section — add one unit test for a helper you care about.
4. After a deploy, do one short exploratory charter in DevSpaces.
5. Open the ISTQB PDF only when you want the verbatim syllabus wording behind a section you liked.

---

*Based on the ISTQB® Certified Tester Foundation Level Syllabus v4.0.1. ISTQB® is a registered trademark of the International Software Testing Qualifications Board. This guide is a non-exam learning aid, not accredited training material.*
