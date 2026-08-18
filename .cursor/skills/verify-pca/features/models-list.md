# List models

`GET /v1/models` returns the served model id so IDEs can select it. The id must match `LLMInferenceService/qwen3-coder` `spec.model.name`.

## Sub-features

- `models-gateway` lists models through RHCL with a valid API key.
- `models-llmd` lists models through the llm-d gateway without a key.

## How to get to it (user POV)

- OpenAI-compatible clients call `GET <base>/models` during setup (Continue/Cline/Roo/OpenCode provider config).
- The catalog must include the configured model (default `Qwen/Qwen3.6-35B-A3B-FP8` unless the LLMIS says otherwise).

## Driving it with verify-pca

Preconditions:

- Doctor `MODE=ai` with `OK=true` and a `MODEL_ID=`. Skip this feature when `AI_NAMESPACE_ACCESS=forbidden` (demo user); OpenCode already has the model from workspace config.
- Gateway list: `DEV_USER` set, `API_KEY_PRESENT=true`, RHCL Accepted, `IDE_VIA=gateway`.

- **RHCL list.** Run `DEV_USER=dev-user1 .cursor/skills/verify-pca/scripts/verify-pca.sh models`. Exit `0`, `STATUS=200`, printed `MODEL_ID_OK=` equals doctor `MODEL_ID`. Body: `artifacts/$RUN_ID/models-body.json`.
- **llm-d list.** Run `VIA=llmd .cursor/skills/verify-pca/scripts/verify-pca.sh models`. Same assertions on a fresh `models-body.json` (set `RUN_ID` or copy the file aside if you need both).
- **Proof.** JSON `data[].id` contains the LLMIS model name. Capture both status and the id list, not only HTTP 200.

## Gotchas

- Gateway `/v1/models` without a key is an auth failure (`api-key-auth`), not a models failure.
- `VIA=llmd … models` needs `oc run` in the AI ns. Forbidden is a skip, not an empty catalog.
- Do not hardcode the model string in assertions; doctor/`MODEL_ID` is the source of truth when the chart override changed the model.
- A 200 with an empty `data` array is a fail.
