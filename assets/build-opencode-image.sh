#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="opencode-build"
BC_NAME="devspaces-opencode"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKERFILE="$SCRIPT_DIR/Dockerfile.opencode"

echo "==> Creating namespace $NAMESPACE (if needed)"
oc create namespace "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

echo "==> Creating BuildConfig $BC_NAME"
oc apply -f - <<EOF
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: $BC_NAME
  namespace: $NAMESPACE
spec:
  output:
    to:
      kind: ImageStreamTag
      name: $BC_NAME:latest
  source:
    type: Dockerfile
    dockerfile: |
$(sed 's/^/      /' "$DOCKERFILE")
  strategy:
    type: Docker
    dockerStrategy:
      from:
        kind: DockerImage
        name: registry.redhat.io/devspaces/udi-rhel8:latest
  triggers: []
---
apiVersion: image.openshift.io/v1
kind: ImageStream
metadata:
  name: $BC_NAME
  namespace: $NAMESPACE
EOF

echo "==> Starting build"
oc start-build "$BC_NAME" -n "$NAMESPACE" --follow

echo "==> Granting image-puller to all DevSpaces namespaces"
for ns in dev1-devspaces dev2-devspaces dev3-devspaces; do
	oc policy add-role-to-group system:image-puller "system:serviceaccounts:$ns" \
		--namespace="$NAMESPACE" 2>/dev/null || true
done

echo "==> Image built and available at:"
echo "    image-registry.openshift-image-registry.svc:5000/$NAMESPACE/$BC_NAME:latest"
