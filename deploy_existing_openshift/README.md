# Deploying on an Existing OpenShift Cluster

Helm value overrides for deploying onto an existing OpenShift cluster (RHOAI, GPU operator, and DevSpaces already installed). Uses charts from `charts`.

| Target | What it deploys |
|--------|-----------------|
| `make ai-serving-deploy-existing-openshift` | AI serving (once per cluster) — namespace, HF token, PVC, LLMInferenceService, Grafana; optional Langfuse + OTel; RHCL AI Gateway front door |
| `make devspace-deploy-existing-openshift` | OpenCode DevWorkspaces as `dev-userN` in `dev-userN-devspaces` (`N=<count>` or single `DEV_USER=`); `TYPE=continue` for Continue/Roo/Cline |

`ai-serving-deploy-existing-openshift` must run first. With `N=`, the first user owns global ConfigMaps in `openshift-devspaces`; later users get `devspacesGlobalConfig.enabled=false` automatically. `N` creates N namespaces (`dev-userN-devspaces`), each with one DevWorkspace named `code-workspace-1` (separate Helm release per user — not one release with N workspaces). Do **not** use `private-assistant-*` as a DevSpace namespace (that prefix is only for AI serving).

### Prerequisite: Red Hat Connectivity Link (RHCL)

Existing OpenShift does **not** install RHCL via make. Before enabling the AI Gateway front door, ensure:

- `rhcl-operator` Subscription is Succeeded (Authorino + Limitador come with it)
- CRDs exist: `authpolicies.kuadrant.io` (and optionally `ratelimitpolicies.kuadrant.io`)
- A `Kuadrant` CR exists (chart creates `kuadrant` in `kuadrant-system` when `aiGateway.kuadrant.create=true`)

Auth for inference is enforced on **`pca-ai-gateway`** (API keys). The llm-d Gateway is annotated `opendatahub.io/managed=false` so OpenShift AI does not attach kubernetesTokenReview AuthPolicies that would break RHCL → llm-d.
IDE traffic defaults to:

`https://pca-ai-gateway-data-science-gateway-class.<AI_NAMESPACE>.svc.cluster.local/v1`

Each DevSpaces namespace gets an API key Secret (`pca-ai-gw-apikey`); the same key is mirrored into the AI serving namespace for AuthPolicy validation (`pca-ai-gw-apikey-<devNamespace>`). Break-glass: `--set aiGateway.escapeHatchToLlmd=true` points IDEs at llm-d directly (no API key).

### Demo DevSpaces (`dev-user1..N`)

```bash
# 1. oc login to your cluster
# 2. Set HF_TOKEN in .env or pass it directly
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx

# 3. Deploy N OpenCode workspaces (syncs values-platform-config instances + Helm)
make devspace-deploy-existing-openshift N=2

# 4. Apply HTPasswd logins (passwords Dev1@PCA2026!, Dev2@PCA2026!, …)
make setup-idp
```

Log in to Dev Spaces via **pca-htpasswd** as `dev-user1` / `Dev1@PCA2026!`. Namespace is always `dev-user1-devspaces`.

Single user (namespace is always `<user>-devspaces`):

```bash
make devspace-deploy-existing-openshift DEV_USER=dev-user2
```

> **OpenCode build:** `opencode-build` is cluster-singleton infrastructure owned by the first Helm release. The Makefile auto-detects whether it already exists and suppresses `opencodeBuild` for subsequent runs. If deploying manually with `helm upgrade --install`, pass `--set opencodeBuild.enabled=false` from the second developer onward.
>
> **Do not uninstall** the release that owns `opencode-build` while other OpenCode workspaces exist — doing so deletes the BuildConfig and ImageStream (the Namespace is kept), breaking image pulls for all running workspaces. Recovery: delete the empty namespace (`oc delete namespace opencode-build`), then re-run any opencode devspace deploy without `--set opencodeBuild.enabled=false` to recreate the full build infrastructure.

## Parameters

| Variable | Default | Used by | Notes |
|----------|---------|---------|-------|
| `AI_NAMESPACE` | `private-assistant-ai-serving` | Both | AI serving namespace (not a DevSpace NS) |
| `N` | *(empty)* | Devspace | When set, deploy `dev-user1..N` in `dev-userN-devspaces` and sync `values-platform-config.yaml` instances (passwords `DevN@PCA2026!`) |
| `DEV_USER` | *(required if N unset)* | Devspace | OpenShift username; namespace is always `<DEV_USER>-devspaces` |
| `TYPE` | `opencode` | Devspace | `opencode` (default) or `continue` (Continue/Roo/Cline) |
| `HF_TOKEN` | from `.env` (`HUGGINGFACE_TOKEN`) | AI serving | HuggingFace token |
| `MCP_ENABLED` | `false` | Both | Enable `pca-mcp` + IDE MCP wiring |
| `HELM_ARGS` | *(empty)* | Both | Extra `helm upgrade --install` flags |

### Common `HELM_ARGS`

| Flag | When |
|------|------|
| `--set devspacesGlobalConfig.enabled=false` | 2nd+ developer (avoid Helm ownership of global ConfigMaps in `openshift-devspaces`) |
| `--set opencodeBuild.enabled=false` | 2nd+ opencode developer — avoids Helm ownership conflict on the shared `opencode-build` namespace (Makefile detects this automatically) |
| `--set pca-observability.langfuse.enabled=true` | Opt in Langfuse (+ OTel) with AI serving |
| `--set guardrails.enabled=true --set guardrails.endpoint=http://guardrails-proxy.<AI_NS>.svc.cluster.local:8080` | Route IDE chat through guardrails on a devspace |
| `--set aiGateway.escapeHatchToLlmd=true` | Skip RHCL; IDEs call llm-d Gateway directly |
| `--set aiGateway.enabled=false` | Disable RHCL front door resources / IDE RHCL URL |

### Related make targets

| Target | Purpose |
|--------|---------|
| `make setup-idp` | HTPasswd IDP from `values-platform-config.yaml` |
| `make mcp-enable` / `make mcp-disable` | Toggle MCP (`AI_NAMESPACE=`, optional `DEV_USER=`) |
| `make ai-serving-undeploy-existing-openshift` | Remove AI serving Helm releases; **keeps** `AI_NAMESPACE` + `model-cache` PVC |
| `make ai-serving-undeploy-existing-openshift DELETE_NAMESPACE=1` | Full wipe (deletes namespace/PVC → cold start next deploy) |
| `make devspace-undeploy-existing-openshift` | Remove one DevSpace (`DEV_USER=` required) |

## Authentication and Identity Provider Configuration

### HTPasswd IDP (Demo / Test Environments)

For demo and test environments, the quickstart provides an HTPasswd identity provider with pre-configured test users.

**Prerequisites:** `oc` (logged in as cluster-admin), `yq`, `htpasswd` (from `httpd-tools`)

**Step 1 — Choose how many demo users** and sync + deploy. Committed `devspaces.instances` in `values-platform-config.yaml` is a **placeholder**; `N=` replaces it with `dev-user1..N` and passwords `DevN@PCA2026!`:

```bash
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx
make devspace-deploy-existing-openshift N=3
```

**Step 2 — Apply HTPasswd** from the rewritten values list:

```bash
make setup-idp
```

This additively patches the OAuth CR (existing identity providers are preserved) and verifies user login. Re-run after changing `N`. Do not run `setup-idp` against the committed PLACEHOLDER entry.

---

## Observability (Grafana + optional Langfuse)

Grafana (boards B/C — latency, KV/GPU) deploys by default with AI serving via `pca-observability`. Existing OpenShift uses Prometheus **namespace** tenancy (`:9092`); ROSA full provision uses **cluster** monitoring (`:9091`).

| Flag | Default | What you get |
|------|---------|--------------|
| `grafana.enabled` | `true` | 1-pod Grafana + boards B/C. Boards A/D when Langfuse is on |
| `pca-observability.langfuse.enabled` | `false` | Langfuse + OTel Collector; wires vLLM OTLP in the same release |
| `pca-observability.langfuse.ioCapture` | `full` | When Langfuse is on: store full prompt/completion via vLLM middleware (async). Set `metadata` for tokens/latency only |

```bash
# Opt in to Langfuse (full I/O capture is default)
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx \
  HELM_ARGS='--set pca-observability.langfuse.enabled=true'

# Routes + secrets
oc get route pca-grafana pca-langfuse -n $AI_NAMESPACE
oc get secret pca-grafana-admin -n $AI_NAMESPACE -o jsonpath='{.data.admin-password}' | base64 -d; echo
oc get secret pca-langfuse-credentials -n $AI_NAMESPACE -o jsonpath='{.data.init-user-password}' | base64 -d; echo
```

**GPU $/hr PLACEHOLDER:** `cost.gpuHourlyUsd: 1.86` is illustrative L40S on-demand — **not** billing truth. Override per cluster and set `cost.gpuHourlyUsdIsPlaceholder: false`.

**Attribution:** Roo + Continue + Cline send `X-PCA-User` / `X-PCA-DevSpace` / optional `X-PCA-Team` (from `devspaces[].team`). Full prompt/completion bodies go to Langfuse when `ioCapture=full`. See `charts/pca-ai-serving/charts/pca-observability/README.md`.

### Combined: Langfuse + MCP

```bash
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx MCP_ENABLED=true \
  HELM_ARGS='--set pca-observability.langfuse.enabled=true'
make devspace-deploy-existing-openshift N=2 MCP_ENABLED=true
```

---

## MCP (Model Context Protocol)

MCP gives AI coding extensions (Continue, Roo Code) live read-only access to cluster state — pods, events, deployments, routes — via natural language tool calls. It is optional and disabled by default.

### Deploy with MCP enabled from the start

Pass `MCP_ENABLED=true` to both the AI serving and devspace make targets:

```bash
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx MCP_ENABLED=true
make devspace-deploy-existing-openshift N=2 MCP_ENABLED=true
```

### Enable MCP on an already-running deployment

```bash
make mcp-enable AI_NAMESPACE=<ai-ns> DEV_USER=dev-user1
```

Then ask the developer to reload Continue in the IDE (`Ctrl+Shift+P` → `Developer: Reload Window`). The `openshift-ai-mcp` server will appear in the MCP panel.

### Verify

```bash
oc get pods -n <ai-ns> | grep openshift-mcp   # should show 1/1 Running
```

### Disable MCP

```bash
make mcp-disable AI_NAMESPACE=<ai-ns> DEV_USER=dev-user1
```

### Adding more data sources

See `charts/pca-platform-config/charts/pca-mcp/README.md` for how to add further MCP servers (MariaDB, Confluence, Jira, GitLab) by enabling the disabled-by-default templates.

---

## OpenCode Devspace (default)

OpenCode is the default AI coding agent (Web UI + TUI). It runs in a DevSpaces workspace using a custom image (`devspaces-opencode`) that ships the OpenCode CLI pre-installed. The workspace exposes port 4096 as a public endpoint for the Web UI.

> **Known limitation — responses appear empty in OpenCode UI:**
> `Qwen3-Coder-30B-A3B-Instruct-FP8` in thinking mode places the entire response (including the actual answer) inside `<think>` reasoning tokens. vLLM's `--reasoning-parser=qwen3` correctly extracts this to the `reasoning` field, leaving `content: null`. OpenCode reads `content` only, so the response area is blank — the answer is visible only by expanding the "Thought" section. This is a model behaviour issue caused by FP8 quantization degrading the reasoning/content split; the full-precision model produces correct output. Continue is unaffected (it surfaces reasoning tokens as visible output). Workaround options: (1) run a local response-transformation proxy that copies `reasoning` → `content` when `content` is null; (2) replace with full-precision model.

### Prerequisites

1. HTPasswd users exist (`make setup-idp` after `N=` sync, or operator-supplied users)
2. Log in to the DevSpaces dashboard as that user (e.g. `dev-user1` via **pca-htpasswd**):
   ```
   https://devspaces.apps.<cluster-domain>/
   ```

### Step 1 — Deploy OpenCode DevSpaces

```bash
make devspace-deploy-existing-openshift N=2
# or one user:
make devspace-deploy-existing-openshift DEV_USER=dev-user1
```

`TYPE` defaults to `opencode`. For Continue/Roo/Cline instead, pass `TYPE=continue` (uses `values-devspaces-continue.yaml`).

This target:
- Uses namespaces `dev-userN-devspaces` only
- Creates the namespace with DevSpaces labels (idempotent)
- Deploys `pca-devspaces` once per user (one `code-workspace-1` per ns; first user may create `opencode-build`)

The DevWorkspace is created with `started: false`.

### Step 2 — Trigger the image build (first time only)

```bash
oc start-build devspaces-opencode -n opencode-build --follow
```

The build installs OpenCode CLI (version pinned via `opencodeBuild.opencodeVersion` in values) and stubs `xdg-open` to prevent crashes in headless environments.

The workspace pod will stay `Pending` until the image is available. Once the build completes, the user starts the workspace from the DevSpaces dashboard. The postStart sequence runs automatically:
1. Writes `~/.config/opencode/opencode.json` from workspace env vars
2. Downloads the OpenCode VS Code extension (`.vsix`)
3. Reads the password from the `opencode-web-password` Secret and starts `opencode web --port 4096` (password-protected)

### Access

After the workspace is `Running 1/1`, the Web UI is available at the `opencode-web` endpoint shown in the DevSpaces dashboard, or via:

```bash
oc get routes -n <username>-devspaces | grep opencode-web
```

The Web UI is password-protected (HTTP Basic Auth, username: `opencode`). Retrieve the password:

```bash
oc get secret opencode-web-password -n <username>-devspaces \
  -o jsonpath='{.data.password}' | base64 -d
```

The password is generated once at first deploy and preserved across `helm upgrade` runs.

The TUI (`opencode`) is available in the workspace terminal — use **Terminal: Create New Terminal (select a container)** and pick `dev-tools` to avoid the DevSpaces cursor focus issue.

### Local terminal (desktop OpenCode)

To connect the local OpenCode desktop app to the cluster llm-d endpoint, configure `~/.config/opencode/opencode.jsonc` with the provider pointing to the external ELB URL. A reference config is baked into the OpenCode image build (`opencodeBuild` in `values-devspaces.yaml`) — the external endpoint can be retrieved with:

```bash
oc get llminferenceservice -n <ai-serving-namespace> -o jsonpath='{.items[0].status.url}'
```

Run with `NODE_TLS_REJECT_UNAUTHORIZED=0 opencode` (ELB cert is self-signed).

Also create `~/.local/share/opencode/auth.json`:
```json
{"vllm":{"type":"api","key":"EMPTY"}}
```

### vLLM context window

OpenCode needs headroom under `--max-model-len` for prompt + completion. All PCA paths set `tokens.total: 32000` (vLLM `--max-model-len`) and `tokens.output: 8192` (OpenCode/IDE completion cap). Keep `pca-ai-serving` and `pca-devspaces` `tokens.*` in sync. If you lower `tokens.total` without lowering OpenCode `limit.output`, chat requests can fail with max_tokens errors.

**Warm model path (avoid multi‑minute cold starts):** Prefer `make ai-serving-deploy-existing-openshift` (upgrade in place) over undeploy. Keep `minReplicas: 1` — do not scale the predictor to 0. Default undeploy only uninstalls Helm releases and **keeps** the namespace + `model-cache` PVC; use `DELETE_NAMESPACE=1` only when you intend a full wipe. `HF_HUB_OFFLINE` is `1` so restarts read weights from the PVC (no Hugging Face). The PVC is also annotated `helm.sh/resource-policy: keep` so `helm uninstall` alone does not delete it. For a brand-new empty PVC, temporarily set `HF_HUB_OFFLINE=0` (or preload the PVC), then set it back to `1`.

---

### Replacing HTPasswd with Enterprise IDP

For production, replace HTPasswd with your organization's identity provider. OpenShift OAuth supports OIDC, LDAP, and SAML (via proxy).

#### Option A: OpenID Connect (OIDC)

Recommended for Azure AD, Okta, Keycloak, Google Workspace, and any OIDC-compliant provider.

1. Register an OAuth client with your OIDC provider:
   - **Redirect URI:** `https://<openshift-oauth-route>/oauth2callback/<provider-name>`
   - Note the Client ID and Client Secret

2. Create the client secret in OpenShift:
   ```bash
   oc create secret generic oidc-client-secret \
     --from-literal=clientSecret=<your-client-secret> \
     -n openshift-config
   ```

3. Patch the OAuth CR to add the OIDC provider:
   ```bash
   oc patch oauth cluster --type=json -p '[{
     "op": "add",
     "path": "/spec/identityProviders/-",
     "value": {
       "name": "enterprise-oidc",
       "mappingMethod": "claim",
       "type": "OpenID",
       "openID": {
         "clientID": "<your-client-id>",
         "clientSecret": {"name": "oidc-client-secret"},
         "issuer": "https://<your-idp-issuer-url>",
         "claims": {
           "preferredUsername": ["preferred_username", "email"],
           "name": ["name"],
           "email": ["email"]
         }
       }
     }
   }]'
   ```

4. Remove the HTPasswd provider (optional):
   ```bash
   # Find the index of the pca-htpasswd provider
   oc get oauth cluster -o json | jq '.spec.identityProviders | to_entries[] | select(.value.name == "pca-htpasswd") | .key'

   # Remove it (replace 0 with the actual index)
   oc patch oauth cluster --type=json -p '[{"op": "remove", "path": "/spec/identityProviders/0"}]'
   ```

#### Option B: LDAP / Active Directory

1. Create the bind password secret:
   ```bash
   oc create secret generic ldap-bind-password \
     --from-literal=bindPassword=<bind-password> \
     -n openshift-config
   ```

2. If using LDAPS with a custom CA, create the CA ConfigMap:
   ```bash
   oc create configmap ldap-ca-bundle \
     --from-file=ca.crt=<path-to-ca-cert> \
     -n openshift-config
   ```

3. Patch the OAuth CR:
   ```bash
   oc patch oauth cluster --type=json -p '[{
     "op": "add",
     "path": "/spec/identityProviders/-",
     "value": {
       "name": "enterprise-ldap",
       "mappingMethod": "claim",
       "type": "LDAP",
       "ldap": {
         "url": "ldaps://ldap.example.com:636/ou=users,dc=example,dc=com?uid",
         "bindDN": "cn=admin,dc=example,dc=com",
         "bindPassword": {"name": "ldap-bind-password"},
         "ca": {"name": "ldap-ca-bundle"},
         "insecure": false,
         "attributes": {
           "id": ["dn"],
           "preferredUsername": ["uid"],
           "name": ["cn"],
           "email": ["mail"]
         }
       }
     }
   }]'
   ```

#### Option C: SAML

OpenShift does not support SAML identity providers natively. To integrate with a SAML IdP:

1. Deploy a SAML-to-OIDC bridge (Keycloak, Dex, or similar) on the cluster
2. Configure the bridge to federate with your SAML IdP
3. Configure OpenShift OAuth with an OIDC provider pointing to the bridge (see Option A)

### User List Alignment

When switching from HTPasswd to enterprise IDP, the `devspaces.instances` list in `values-platform-config.yaml` still drives namespace and RBAC creation. Update the `user` fields to match the identity provider's username claim (e.g., `preferredUsername` for OIDC, `uid` for LDAP). Passwords can be removed since they are only used by the HTPasswd setup script.

### Dev Spaces Authentication

Dev Spaces inherits the cluster IDP automatically. Once users can `oc login`, they can access the Dev Spaces dashboard and create workspaces. Per-user namespace isolation is handled by the DevWorkspace controller using the authenticated user identity.

## RHCL AI Gateway follow-ups (not Phase 1)

Documented for later work — charts already stub the values:

| Topic | Values stub | Notes |
|-------|-------------|--------|
| Rate / token limits | `aiGateway.rateLimits.enabled` | `RateLimitPolicy` / `TokenRateLimitPolicy` on `pca-ai-gateway` |
| Front-door HA | `aiGateway.ha.replicas` | Scale the Gateway Deployment beyond 1 replica |
| Other-cluster / external backends | `aiGateway.backends.otherCluster` / `external` | Enable + route by OpenAI `model` name |
| Key audit | — | Optional per-developer key lifecycle beyond shared AuthPolicy accept-list |
