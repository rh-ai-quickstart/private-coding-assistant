# API key auth

RHCL rejects unauthenticated chat and accepts the per-DevSpace key from secret `pca-ai-gw-apikey` (key `api_key`). Auth runs before guardrails: a missing key never reaches the proxy.

## Sub-features

- `auth-missing` returns 401 or 403 with no `Authorization` header.
- `auth-invalid` returns 401 or 403 with `Bearer invalid-smoke-test-key`.
- `auth-valid` returns 200 with the DevSpaces secret key.

## How to get to it (user POV)

- IDE extensions send `Authorization: Bearer <key>` to the RHCL `/v1` base URL. The key is provisioned into the DevSpaces namespace (and mirrored into the AI namespace). Users do not mint keys by hand.
- A request with no key or a wrong key must not reach a model completion on RHCL.

## Driving it with verify-pca

Preconditions:

- Doctor `MODE=ai` (`AI_NAMESPACE_ACCESS=ok` and can `oc run` curl pods). If `MODE=devspace` or `AI_NAMESPACE_ACCESS=forbidden`, skip this whole feature and say Forbidden, not "auth broken".
- `verify-pca.sh doctor` prints `OK=true`, `AI_GATEWAY_PRESENT=true`, `AI_GATEWAY_ACCEPTED=True`.
- `DEV_USER` set and `API_KEY_PRESENT=true` for the valid-key case.
- Request JSON is a tiny chat (`max_tokens` 8 is enough for reject cases).

- **Missing key.** POST chat with no Authorization. Run `HTTP_BODY_FILE=<request.json> HTTP_INSECURE=1 .cursor/skills/verify-pca/scripts/verify-pca.sh http POST "https://pca-ai-gateway-data-science-gateway-class.${AI_NAMESPACE}.svc.cluster.local/v1/chat/completions"` with a request file that has `model`, `messages`, `stream: false`, `max_tokens: 8` and **no** `HTTP_HEADER`. Observable: `STATUS=401` or `STATUS=403`. Save body as `artifacts/$RUN_ID/auth-missing.json`.
- **Invalid key.** Same POST with `HTTP_HEADER='Authorization: Bearer invalid-smoke-test-key'`. Observable: `STATUS=401` or `STATUS=403`. Save `auth-invalid.json`.
- **Valid key.** Run `DEV_USER=dev-user1 VIA=gateway .cursor/skills/verify-pca/scripts/verify-pca.sh chat`. Observable: `STATUS=200` and non-empty assistant text. This is the positive control; do not skip it after the rejects when this feature is in scope.
- **Proof.** Evidence dir contains missing, invalid, and valid status files. Valid response is JSON with `choices`. No file contains the real API key.

## Gotchas

- llm-d has no API key. `VIA=llmd` succeeding does not prove RHCL auth.
- 200 on a missing key is a product regression, not a flake.
- Do not print `oc get secret pca-ai-gw-apikey -o yaml` into the transcript.
- AuthPolicy name is `pca-ai-gateway-apikey`; HTTPRoute `pca-ai-gateway-local`. If those are missing, doctor/`AI_GATEWAY` checks failed — stop (in `MODE=ai` only).
