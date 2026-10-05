# PCA Assets — Custom DevSpaces Image & Devfile

## Contents

| File | Purpose |
|------|---------|
| `Dockerfile.opencode` | Custom DevSpaces image with OpenCode v1.15.13 pre-installed and configured for private AI Gateway |
| `devfile.yaml` | DevSpaces workspace template — appears on the DevSpaces dashboard as a launchable sample |
| `build-opencode-image.sh` | Script to build the custom image on any OpenShift cluster |

## Image Details

- **Base**: `registry.redhat.io/devspaces/udi-rhel8:latest` (Red Hat Universal Developer Image)
- **Added**: OpenCode v1.15.13 CLI, pre-configured for the cluster-internal llm-d AI Gateway
- **Endpoint**: `https://llm-d-gateway-data-science-gateway-class.ai-serving.svc.cluster.local/v1`
- **Model**: `Qwen/Qwen3.6-35B-A3B-FP8`
- **SHA**: `sha256:dcb6b1cee00115467e6c5432930416a7e8b868b6a8e5ee3075ce6823ff7e2e98`

## Building on a New Cluster

The Helm chart in `charts/pca-devspaces/` automatically creates a BuildConfig
and triggers the image build. For manual builds:

```bash
./build-opencode-image.sh
```

The image is stored in the internal OpenShift registry at:
```
image-registry.openshift-image-registry.svc:5000/opencode-build/devspaces-opencode:latest
```
