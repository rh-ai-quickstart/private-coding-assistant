# Customization

Configuration-only customizations for implementation engagements. The Helm charts and operators stay the supported upgrade path; tune prompts, rules, and workspace templates rather than forking the platform.

## System prompts and context

Continue, Cline, and Roo Code accept custom system prompts. Deliver them through the Dev Spaces ConfigMaps owned by `pca-devspaces` so every workspace gets the same baseline (languages, internal libraries, architecture rules, logging/test standards).

## Per-repository rules

| Extension | Rules location |
|-----------|----------------|
| Continue | `.continuerules` |
| Cline | `.clinerules` |
| Roo Code | `.roo/rules/`, `.roo/rules-{mode}/` |

Commit rules next to application code so AI context evolves with the repo.

## DevWorkspace templates

Offer stack-specific DevWorkspace images/templates (Java, Python, Node, Go, IaC) from the Dev Spaces dashboard so developers pick a ready environment instead of installing toolchains locally. See `assets/devfile.yaml` and OpenCode image assets under [`assets/`](../assets/).

## MCP and internal systems

Optional MCP servers (docs, OpenAPI catalogs, issue trackers, SCM search) can be wired via `pca-mcp` and IDE ConfigMaps. Enablement is documented in [deploy_existing_openshift/README.md](../deploy_existing_openshift/README.md).

## Quality gates (e.g. SonarQube)

Encode the customer’s quality profile as plain-language constraints in the system prompt or rules files so generation aligns with the gate before commit. Export rules from the customer’s SonarQube/SonarCloud profile; do not hard-code a sample “ACME” profile into the platform charts.

## Related

- [IDE and extensions](ide-and-extensions.md)
- Chart: `charts/pca-devspaces`
