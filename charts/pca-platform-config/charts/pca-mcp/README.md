# pca-mcp

MCP (Model Context Protocol) server deployment for the Private AI Code Assistant.

Deploys the **Red Hat OpenShift MCP server** (`kubernetes-mcp-server`) as a plain Deployment + ClusterIP Service. This gives AI coding extensions (Continue, Roo Code) live read-only access to cluster state — pods, events, deployments, namespaces — via natural language.

> **Note on the MCPServer CR (mcp.x-k8s.io/v1alpha1):** The MCP Lifecycle Operator is Developer Preview in RHOAI 3.4 and has a known bug where its embedded default config references `$CONFIG_PATH` literally, causing pods to crash on startup regardless of env var overrides. This chart uses plain Deployment + Service instead, which is functionally equivalent and fully production-ready.

## What Gets Deployed

| Resource | Details |
|---|---|
| `Deployment/openshift-mcp` | `kubernetes-mcp-server` image, read-only cluster access, port 8080 |
| `Service/openshift-mcp` | ClusterIP only — zero external egress |
| `ClusterRole/mcp-openshift-viewer` | Read-only access to pods, events, deployments, routes, etc. |
| `ServiceAccount/mcp-openshift-sa` | Used by the pod for in-cluster Kubernetes API access |

Endpoints exposed by the server: `/sse` (SSE transport), `/mcp` (streamable HTTP), `/healthz`, `/stats`, `/metrics`

## Prerequisites

No operator installation required. The chart is self-contained.

Optional — to verify if the MCP Lifecycle Operator is present on your cluster (not required by this chart):
```bash
oc get crd mcpservers.mcp.x-k8s.io
```

## Enabling MCP

Add to your Helm values override:

```yaml
mcp:
  enabled: true

pca-mcp:
  namespace: <your-ai-serving-namespace>   # must match your deployment namespace
  gateway:
    enabled: false                          # MCP Gateway CRDs not yet available on most clusters
```

Example upgrade command:
```bash
helm upgrade <release-name> ./charts/pca-platform-config \
  --reuse-values \
  --set mcp.enabled=true \
  --set pca-mcp.gateway.enabled=false \
  --set pca-mcp.namespace=<your-namespace>
```

## Continue / Roo Code Extension Config

When `mcp.enabled=true` is also set on the `pca-devspaces` chart, the `mcpServers` block is automatically injected into the Continue `config.yaml` and Roo Code `mcp_settings.json`:

```yaml
# Continue v2 format (flat — no transport: nesting)
mcpServers:
  - name: "openshift-ai-mcp"
    type: sse
    url: "http://openshift-mcp.<namespace>.svc.cluster.local:8080/sse"
```

After upgrading the devspaces chart, **reload the Continue window** (`Ctrl+Shift+P` → `Developer: Reload Window`) to pick up the new config.

## Adding More MCP Servers

To add a server for another data source (e.g. MariaDB, Confluence, Jira):

1. **Find the image** in the [Red Hat MCP Catalog](https://www.redhat.com/en/products/ai/openshift-ai/mcp-servers) (OpenShift AI Hub → MCP tab) or use a community image.

2. **Mirror the image** to your registry if air-gapped:
   ```bash
   podman pull <source-image> --platform=linux/amd64
   podman push <your-registry>/<org>/<name>:<tag> --platform=linux/amd64
   ```

3. **Create a Secret** with required credentials:
   ```bash
   oc create secret generic my-datasource-secret \
     --from-literal=API_TOKEN=<token> \
     -n <namespace>
   ```

4. **Add a Deployment + Service template** under `templates/mcpserver-<name>.yaml` following the pattern in `mcpserver-mariadb.yaml` (disabled by default as a reference).

5. **Enable it via values**:
   ```yaml
   pca-mcp:
     mariadb:
       enabled: true
       host: "mariadb.my-namespace.svc.cluster.local"
       secretName: my-datasource-secret
   ```

6. **Add the mcpServers entry** in the devspaces chart values so extensions discover it.

## Available Servers (Red Hat MCP Catalog)

| Tier | Server | Use Case |
|---|---|---|
| Red Hat | **OpenShift** (deployed by this chart) | Cluster state — pods, events, deployments, routes |
| Red Hat | Ansible Automation Platform | Trigger playbooks, check job status |
| Red Hat | Lightspeed | Platform intelligence and recommendations |
| Partner | Microsoft Azure | Azure resource management |
| Partner | Dynatrace | Real-time performance insights |
| Community | MariaDB | DB schema + query — useful for coding context |
| Community | MongoDB | Document collection queries |

Source: [Red Hat MCP Catalog](https://www.redhat.com/en/products/ai/openshift-ai/mcp-servers)

## Troubleshooting

**Pod crashes with `open $CONFIG_PATH: no such file or directory`**
The image bakes in `CONFIG_PATH=/mcp_config.toml` as default env. The chart passes `--config /mcp_config.toml` explicitly as a CLI arg to override this. If you see this error, ensure the arg is present in the Deployment spec.

**Continue shows "No MCP servers configured" after enabling**
Continue v2 uses a flat format — `type` and `url` are top-level fields on the server object. Do **not** use the `transport:` nesting (that was the v1 format). After any config change, run `Developer: Reload Window` in the IDE.

**Pod is Running but not Ready**
The readiness probe hits `/healthz` (not `/health`). Verify the probe path in the Deployment spec.
