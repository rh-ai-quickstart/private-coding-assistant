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
