#!/usr/bin/env bash
# seal-secret.sh — Helper to create a Sealed Secret from a Kubernetes secret YAML.
# Requires: kubeseal CLI + Sealed Secrets controller installed on the cluster.
#
# Usage:
#   ./scripts/seal-secret.sh <input-secret.yaml> <output-sealed-secret.yaml>
#
# Example:
#   echo -n 'hf_abc123' | kubectl create secret generic hf-token \
#     --namespace=ai-serving --from-file=token=/dev/stdin --dry-run=client -o yaml \
#     | ./scripts/seal-secret.sh /dev/stdin argocd/02-platform-config/hf-token-sealed.yaml

set -euo pipefail

INPUT="${1:?Usage: seal-secret.sh <input.yaml> <output.yaml>}"
OUTPUT="${2:?Usage: seal-secret.sh <input.yaml> <output.yaml>}"

if ! command -v kubeseal &>/dev/null; then
  echo "ERROR: kubeseal CLI not found. Install from: https://github.com/bitnami-labs/sealed-secrets/releases"
  exit 1
fi

kubeseal --format yaml \
  --controller-name sealed-secrets \
  --controller-namespace kube-system \
  < "${INPUT}" \
  > "${OUTPUT}"

echo "Sealed secret written to: ${OUTPUT}"
echo "This file is safe to commit to Git."
