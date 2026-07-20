# Deploying on an Existing OpenShift Cluster

This directory contains Helm values overrides for deploying the Private AI Code Assistant on an existing OpenShift cluster (where operators and platform resources are already provisioned).

## Authentication and Identity Provider Configuration

### HTPasswd IDP (Demo / Test Environments)

For demo and test environments, the quickstart provides an HTPasswd identity provider with pre-configured test users.

**Prerequisites:** `oc` (logged in as cluster-admin), `yq`, `htpasswd` (from `httpd-tools`)

**Step 1 — Configure users** in `values-platform-config.yaml`:

```yaml
devspaces:
  instances:
    - namespace: dev-user1-devspaces
      name: code-workspace-1
      user: dev-user1
      password: "Dev1@PCA2026!"
    - namespace: dev-user2-devspaces
      name: code-workspace-2
      user: dev-user2
      password: "Dev2@PCA2026!"
    - namespace: dev-user3-devspaces
      name: code-workspace-3
      user: dev-user3
      password: "Dev3@PCA2026!"
```

**Step 2 — Run the IDP setup script:**

```bash
make setup-idp
```

This additively patches the OAuth CR (existing identity providers are preserved) and verifies user login.

**Step 3 — Deploy the platform and AI serving stack:**

```bash
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx
```

This deploys the AI serving backend. Then deploy devspaces per developer:

```bash
make devspace-deploy-existing-openshift DEV_NAMESPACE=dev-user1-devspaces AI_NAMESPACE=private-assistant-ai-serving
```

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

**Attribution:** Roo + Continue + Cline send `X-PCA-User` / `X-PCA-DevSpace` / optional `X-PCA-Team` (from `devspaces[].team`). Full prompt/completion bodies go to Langfuse when `ioCapture=full`. See `PCA_Deployment_ROSA/charts/pca-ai-serving/charts/pca-observability/README.md`.

### Combined: Langfuse + MCP

```bash
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx MCP_ENABLED=true \
  HELM_ARGS='--set pca-observability.langfuse.enabled=true'
make devspace-deploy-existing-openshift DEV_NAMESPACE=<dev-ns> MCP_ENABLED=true
```

---

## MCP (Model Context Protocol)

MCP gives AI coding extensions (Continue, Roo Code) live read-only access to cluster state — pods, events, deployments, routes — via natural language tool calls. It is optional and disabled by default.

### Deploy with MCP enabled from the start

Pass `MCP_ENABLED=true` to both the AI serving and devspace make targets:

```bash
make ai-serving-deploy-existing-openshift HF_TOKEN=hf_xxx MCP_ENABLED=true
make devspace-deploy-existing-openshift DEV_NAMESPACE=<dev-ns> MCP_ENABLED=true
```

### Enable MCP on an already-running deployment

```bash
make mcp-enable AI_NAMESPACE=<ai-ns> DEV_NAMESPACE=<dev-ns>
```

Then ask the developer to reload Continue in the IDE (`Ctrl+Shift+P` → `Developer: Reload Window`). The `openshift-ai-mcp` server will appear in the MCP panel.

### Verify

```bash
oc get pods -n <ai-ns> | grep openshift-mcp   # should show 1/1 Running
```

### Disable MCP

```bash
make mcp-disable AI_NAMESPACE=<ai-ns> DEV_NAMESPACE=<dev-ns>
```

### Adding more data sources

See `PCA_Deployment_ROSA/charts/pca-platform-config/charts/pca-mcp/README.md` for how to add further MCP servers (MariaDB, Confluence, Jira, GitLab) by enabling the disabled-by-default templates.

---

## OpenCode Devspace

OpenCode is an AI coding agent with a Web UI and TUI. It runs in a dedicated DevSpaces workspace using a custom image (`devspaces-opencode`) that ships the OpenCode CLI pre-installed. The workspace exposes port 4096 as a public endpoint for the Web UI.

> **Known limitation — responses appear empty in OpenCode UI:**
> `Qwen3-Coder-30B-A3B-Instruct-FP8` in thinking mode places the entire response (including the actual answer) inside `<think>` reasoning tokens. vLLM's `--reasoning-parser=qwen3` correctly extracts this to the `reasoning` field, leaving `content: null`. OpenCode reads `content` only, so the response area is blank — the answer is visible only by expanding the "Thought" section. This is a model behaviour issue caused by FP8 quantization degrading the reasoning/content split; the full-precision model produces correct output. Continue is unaffected (it surfaces reasoning tokens as visible output). Workaround options: (1) run a local response-transformation proxy that copies `reasoning` → `content` when `content` is null; (2) replace with full-precision model.

### Prerequisites

1. The target user must exist (`oc get user <username>`)
2. The user must have logged into the DevSpaces dashboard at least once to trigger namespace auto-provisioning:
   ```
   https://devspaces.apps.<cluster-domain>/
   ```

### Step 1 — Build the custom OpenCode image

The `opencode-image-build.yaml` template creates the build infrastructure in the `opencode-build` namespace. It is included in the `pca-devspaces` chart and deployed as part of the OpenCode devspace release. Trigger the build after the first deploy:

```bash
oc start-build devspaces-opencode -n opencode-build --follow
```

The build installs OpenCode CLI (version pinned via `opencodeBuild.opencodeVersion` in values) and bakes the llm-d provider config into the image.

### Step 2 — Deploy the OpenCode devspace

```bash
make devspace-opencode-deploy-existing-openshift \
  DEV_NAMESPACE=<username>-devspaces \
  AI_NAMESPACE=<ai-serving-namespace> \
  DEV_USER=<username>
```

This target:
- Creates the namespace with DevSpaces labels (idempotent — safe if it already exists)
- Deploys `pca-devspaces` chart using `values-devspaces-opencode.yaml`

The DevWorkspace is created with `started: false`. The user starts it from the DevSpaces dashboard.

### Step 3 — Trigger the image build (first time only)

```bash
oc start-build devspaces-opencode -n opencode-build --follow
```

The workspace pod will stay `Pending` until the image is available. Once the build completes and the user starts the workspace, the postStart sequence runs:
1. Writes `~/.config/opencode/opencode.json` from workspace env vars
2. Downloads the OpenCode VS Code extension (`.vsix`)
3. Starts `opencode web --port 4096 --hostname 0.0.0.0`

### Access

After the workspace is `Running 1/1`, the Web UI is available at the `opencode-web` endpoint shown in the DevSpaces dashboard, or via:

```bash
oc get routes -n <username>-devspaces | grep opencode-web
```

The Web UI is password-protected (HTTP Basic Auth). Credentials:

- **Username**: `opencode`
- **Password**: retrieve with:

```bash
oc get secret opencode-web-password -n <username>-devspaces \
  -o jsonpath='{.data.password}' | base64 -d
```

The password is generated once at first deploy and preserved across `helm upgrade` runs.

The TUI (`opencode`) is available in the workspace terminal — use **Terminal: Create New Terminal (select a container)** and pick `dev-tools` to avoid the DevSpaces cursor focus issue.

### Local terminal (desktop OpenCode)

To connect the local OpenCode desktop app to the cluster llm-d endpoint, configure `~/.config/opencode/opencode.jsonc` with the provider pointing to the external ELB URL. A reference config is at `deploy_existing_openshift/values-devspaces-opencode.yaml` — the external endpoint can be retrieved with:

```bash
oc get llminferenceservice -n <ai-serving-namespace> -o jsonpath='{.items[0].status.url}'
```

Run with `NODE_TLS_REJECT_UNAUTHORIZED=0 opencode` (ELB cert is self-signed).

Also create `~/.local/share/opencode/auth.json`:
```json
{"vllm":{"type":"api","key":"EMPTY"}}
```

### vLLM context window

The default `--max-model-len=32768` is insufficient — OpenCode requests 32000 output tokens by default, leaving no room for the prompt. `values-ai-serving.yaml` sets `vllm.maxModelLen: 49152`. If you redeploy AI serving without this override, OpenCode will enter a session compaction loop.

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
