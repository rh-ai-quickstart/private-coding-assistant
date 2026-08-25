# pca-semantic-router

Optional OpenAI-compatible hop that picks local llm-d vs an external provider.

Not an OpenShift AI DSC component. Enable with `semanticRouter.enabled=true,global.semanticRouter.enabled=true` on `pca-ai-serving`. Default is off: TrustyAI pins llm-d HTTP :80 (pin local).

`routeMode: pin-local` always uses llm-d. `routeMode: auto` needs `external.baseUrl` plus Secret `pca-semantic-router-external` in the AI namespace. Provider keys never go in DevSpaces.

This chart is an HTTP API-mode stand-in. Swap the Deployment image later for the full vLLM Semantic Router stack if needed.
