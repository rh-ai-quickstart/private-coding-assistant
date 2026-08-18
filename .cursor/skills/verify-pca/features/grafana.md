# Grafana

Operators open PCA Grafana to see serving dashboards. The app is healthy when `/api/health` succeeds and the route exists.

## Sub-features

- `grafana-health` returns HTTP 200 from in-cluster Grafana `/api/health`.
- `grafana-route` exposes route `pca-grafana` with a non-empty host.
- `grafana-dashboards` (optional) ConfigMaps `pca-grafana-dashboard-b` and `pca-grafana-dashboard-c` exist.

## How to get to it (user POV)

- Open the `pca-grafana` route in a browser and log in as `admin` with the password from secret `pca-grafana-admin` key `admin-password`.
- Dashboards B/C are the default serving boards. A/D exist when Langfuse is enabled.

## Driving it with verify-pca

Preconditions:

- Doctor `OK=true` and `MODE=ai`. If `AI_NAMESPACE_ACCESS=forbidden`, skip Grafana (demo users cannot `oc run` there) and stop.

- **Health.** Run `.cursor/skills/verify-pca/scripts/verify-pca.sh grafana-health`. Exit `0`, `STATUS=200`. Body `artifacts/$RUN_ID/grafana-health.json` (often `database: ok`). Printed `GRAFANA_ROUTE=` is non-empty when the route exists.
- **Route.** Same command prints `GRAFANA_ROUTE`. Optionally open `https://<host>` in a browser; screenshot must show Grafana, not an oauth-proxy error page alone.
- **Dashboards (optional).** `oc get configmap pca-grafana-dashboard-b pca-grafana-dashboard-c -n $AI_NAMESPACE`. Do not dump dashboard JSON into evidence.
- **Proof.** Health 200 plus route host. Do not write `admin-password` into artifacts. A Prometheus `/api/ds/query` check lives in `make smoke COMPONENT=grafana`; only required when the change is Grafana datasource/tenancy.

## Gotchas

- Grafana may sit behind OpenShift oauth-proxy on the route; in-cluster `pca-grafana:3000` is the health path this helper uses.
- Legacy Grafana datasource proxy GET often 400 against Thanos namespace tenancy. Do not use that path as proof; smoke uses `POST /api/ds/query`.
- Missing Grafana is a skip for this feature, not a serving outage.
