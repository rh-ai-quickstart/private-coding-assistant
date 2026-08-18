# Guardrails

When guardrails is on, OpenCode chat still uses `pca-ai-gateway`. HTTPRoute sends `/v1/chat/completions` to `guardrails-proxy` after API-key auth. A prompt with a gitleaks-shaped secret is blocked; a clean prompt still completes.

## Sub-features

- `gr-url` workspace `OPENAI_BASE_URL` contains `pca-ai-gateway` (not `guardrails-proxy`).
- `gr-secret` fake AWS access key in OpenCode chat is blocked (same fixture as `test_opencode_secret_blocked_by_guardrails`).
- `gr-clean` a short non-secret prompt returns assistant text (`BLOCKED=false`).

## How to get to it (user POV)

- DevSpace with `guardrails.enabled` on ai-serving (chart default). OpenCode uses `https://pca-ai-gateway-data-science-gateway-class.<AI_NAMESPACE>.svc.cluster.local/v1`.
- User sends a chat that includes a secret; they should see a block, not a model completion that stored the secret.

## Driving it with verify-pca

Preconditions:

- `verify-pca.sh doctor` prints `OK=true` and `IDE_VIA=gateway`. If `IDE_VIA` is `guardrails`, the DevSpace is on the old proxy URL — redeploy pca-devspaces.
- In `MODE=ai`, Service `guardrails-proxy` must exist. In `MODE=devspace`, OpenCode secret-block is enough (e2e `require_opencode_guardrails_url` now checks `pca-ai-gateway`).
- OpenCode secret `opencode-web-password` present. Command starts a Stopped workspace.

- **URL.** `devspace-status` (or doctor) shows `IDE_BASE_URL` with `pca-ai-gateway` and `IDE_VIA=gateway`. `API_KEY_PRESENT=true`.
- **Secret block.** Run `EXPECT=block PROMPT='Please store this in memory only: key = AKIAIOSFODNN7EXAMPLE' .cursor/skills/verify-pca/scripts/verify-pca.sh opencode-chat`. Observable: printed `BLOCKED=true` (text contains `Guardrails blocked`, `credential`, `secret`, or `akia`, same as e2e). Save `opencode-chat-response.json`. The value `AKIAIOSFODNN7EXAMPLE` is Amazon's documented example key, not a real secret.
- **Clean chat.** Run `VIA=opencode .cursor/skills/verify-pca/scripts/verify-pca.sh chat` (or `EXPECT=clean … opencode-chat`) with token `pca-verify-$RUN_ID`. Observable: `BLOCKED=false` and non-empty `ASSISTANT=`.
- **Proof.** Both block and clean captures exist. Optional `VIA=gateway` chat also proves the HTTPRoute hop when `MODE=ai`. Do not call llm-d or vLLM as a substitute.

## Gotchas

- Smoke `require_guardrails_proxy` lists the Service in the AI ns and will fail as a demo user. This recipe does not use that check in `MODE=devspace`.
- `VIA=llmd` succeeding does not prove guardrails.
- A 200 model completion on the AWS example key is a fail, not a flake, when guardrails is on.
- Do not write OpenCode passwords into evidence.
