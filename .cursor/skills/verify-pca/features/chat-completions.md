# Chat completions

Chat completions is the IDE inference path: a developer (or extension) sends a chat and gets a non-empty assistant message from the on-cluster model.

## Sub-features

- `chat-opencode` completes a short prompt through OpenCode Web (port 4096), which calls workspace `OPENAI_BASE_URL`.
- `chat-gateway` completes a short prompt through RHCL with a per-DevSpace API key and `X-PCA-*` headers.
- `chat-llmd` completes the same OpenAI shape through the llm-d gateway (no API key; escape hatch).
- `chat-stream` is optional; default proof is non-streaming.

## How to get to it (user POV)

- Log in as `dev-userN`, open Dev Spaces, start `code-workspace-1`, chat in OpenCode. The workspace `OPENAI_BASE_URL` is `https://pca-ai-gateway-data-science-gateway-class.<AI_NAMESPACE>.svc.cluster.local/v1` when the gateway is on.
- With `guardrails.enabled`, that same URL still applies. HTTPRoute sends `/v1/chat/completions` to `guardrails-proxy` after API-key auth.
- Break-glass: point the IDE at `https://llm-d-gateway-data-science-gateway-class.<AI_NAMESPACE>.svc.cluster.local/v1` when `aiGateway.escapeHatchToLlmd=true`.

## Driving it with verify-pca

Preconditions:

- `verify-pca.sh doctor` prints `OK=true`.
- For `chat-opencode`: `DEV_USER` inferred or set; OpenCode secret `opencode-web-password` present. Doctor `MODE=devspace` selects this path. Command starts a Stopped workspace (same as `tests/e2e`).
- For `chat-gateway`: doctor `MODE=ai`, `IDE_VIA=gateway`, `API_KEY_PRESENT=true`, `AI_GATEWAY_ACCEPTED=True`.
- For `chat-llmd`: doctor `MODE=ai` and llm-d gateway Accepted.

- **OpenCode chat.** Run `VIA=opencode .cursor/skills/verify-pca/scripts/verify-pca.sh chat`. Exit `0`, printed `ASSISTANT=` non-empty, `BLOCKED=false`. Evidence: `opencode-chat-request.json` / `opencode-chat-response.json` (no password).
- **Gateway chat.** Run `DEV_USER=dev-user1 VIA=gateway .cursor/skills/verify-pca/scripts/verify-pca.sh chat`. Exit `0`, `STATUS=200`, `ASSISTANT=` non-empty. Evidence: `chat-request.json` and `chat-response.json`.
- **llm-d chat.** Run `VIA=llmd .cursor/skills/verify-pca/scripts/verify-pca.sh chat`. Exit `0`, `STATUS=200`, non-empty assistant text. Skip when `AI_NAMESPACE_ACCESS=forbidden`.
- **Proof.** Response has assistant text (`choices` content/reasoning, or OpenCode `ASSISTANT=`). Request includes token `pca-verify-$RUN_ID`. Do not store Bearer or OpenCode passwords.

## Gotchas

- Default `chat` in `MODE=ai` hits RHCL. Use `VIA=opencode` when proving the workspace Web API. Use `VIA=llmd` only for the escape hatch.
- Gateway chat without `DEV_USER`/`DEV_NAMESPACE` fails looking up secret `pca-ai-gw-apikey`. That is a missing precondition, not a product outage.
- If `AI_GATEWAY_PRESENT=false`, report `chat-gateway` unreachable. Do not count `VIA=llmd` or OpenCode as RHCL proof.
- Cold vLLM after scale-from-zero can exceed 180s; doctor `WORKLOAD_POD_RUNNING=false` (in `MODE=ai`) means do not chat yet.
- Do not overlap `make performance-vllm` — shared GPU, proofs become timeouts.
- Streaming (`stream: true`) returns SSE `data:` lines, not a single JSON object. Use non-stream for gateway/llm-d proof.
