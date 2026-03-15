# Shared Templates

Canonical reusable templates that are composed into platform-specific wrappers.

- `personas/*.md.tmpl` contains the source content for agent personas.
- Platform wrappers (for example `templates/copilot/agents/*.agent.md.tmpl`) should keep platform metadata/frontmatter and include a shared persona body via `{{#include shared/personas/<name>.md.tmpl}}`.
- Add new persona content here first, then reference it from any platform wrapper templates.
