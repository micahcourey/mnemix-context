# Mnemix Context — Development Guidelines

> These instructions are for AI agents and developers working **on Mnemix Context itself** (templates, generator, skills, agents). They are NOT the generated `copilot-instructions.md` that end-user projects receive.

---

## Project Overview

**Mnemix Context** is a generic, config-driven toolkit that generates AI coding resources (agents, skills, context files, platform adapters) for any software project.

| Layer | Technology |
|-------|-----------|
| Generator | Python 3 (`setup/generate.py`) |
| Templates | Mustache-like `{{placeholder}}` syntax (`.tmpl` files) |
| Config | YAML (`toolkit.config.yaml`) |
| Output | Markdown, YAML, JSONL, shell scripts |
| CI | GitHub Actions |

---

## Versioning Protocol (MANDATORY)

This toolkit follows [Semantic Versioning](https://semver.org/). **Every PR that changes templates, setup scripts, or the generator MUST:**

1. **Bump** the version in the `VERSION` file (root of repo)
2. **Add** an entry to `CHANGELOG.md` under `[Unreleased]`

CI will block PRs that skip this. The current version is in the `VERSION` file.

### What Bump to Use

| Bump | When | Examples |
|------|------|----------|
| **Patch** (`0.x.Y`) | Bug fixes, typo corrections, wording tweaks | Fix broken template conditional, correct WCAG reference |
| **Minor** (`0.X.0`) | New features, backward-compatible changes | Add a new skill/agent, new config field, template rewrite |
| **Major** (`X.0.0`) | Breaking changes that require user action | Config schema restructure, output directory changes |

### What Does NOT Require a Bump

- Changes to `README.md`, `CONTRIBUTING.md`, and other documentation-only files
- Changes to `setup/examples/` configs
- Changes to CI workflows (`.github/workflows/`)
- Changes to this file (`.github/copilot-instructions.md`)

### CHANGELOG Format

Follow [Keep a Changelog](https://keepachangelog.com/):

```markdown
## [Unreleased]

### Added
- New accessibility-audit skill reference file for WCAG 2.2

### Fixed
- Template conditional in security-patterns.md.tmpl
```

Use sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.

---

## Repository Structure

```
mnemix-context/
├── VERSION                          # Semver (e.g., "0.1.0")
├── CHANGELOG.md                     # Keep a Changelog format
├── toolkit.config.yaml              # Config schema (users edit this per project)
├── setup/
│   ├── generate.py                  # Template engine (Python 3)
│   ├── generate.sh                  # Shell wrapper
│   ├── bootstrap.agent.md           # Interactive setup agent
│   ├── tests/                       # Unit tests for generate.py
│   └── examples/                    # Starter configs
├── templates/
│   ├── universal/                   # Open-standard templates (all platforms)
│   │   ├── AGENTS.md.tmpl           # L1 Router
│   │   ├── instructions/            # L2 Instruction modules
│   │   ├── context/                 # L3 Context stubs
│   │   ├── update/                  # Context updater agent
│   │   └── skills/*/SKILL.md.tmpl   # Skills (12 currently)
│   ├── copilot/                     # GitHub Copilot platform
│   │   ├── copilot-instructions.md.tmpl
│   │   ├── agents/*.agent.md.tmpl   # Agent wrappers (frontmatter + include)
│   │   └── prompts/*.prompt.md.tmpl # Reusable prompts
│   ├── opencode/                    # OpenCode native integration
│   │   ├── opencode.json.tmpl       # Project config (model, agents.path, etc.)
│   │   └── agents/*.md.tmpl         # Agent wrappers (frontmatter + include)
│   ├── shared/                      # Canonical reusable templates
│   │   └── personas/*.md.tmpl       # Persona source content
│   └── adapters/                    # Platform adapter templates
├── reference/                       # User drops reference material here (git-ignored)
├── .github/
│   ├── copilot-instructions.md      # THIS FILE — toolkit dev guidelines
│   ├── pull_request_template.md     # PR template with versioning checklist
│   └── workflows/                   # CI workflows
└── README.md
```

---

## Template Development

### Template Syntax

Templates use `{{placeholder}}` syntax rendered by `generate.py`:

| Syntax | Purpose | Example |
|--------|---------|---------|
| `{{key}}` | Simple substitution | `{{project.name}}` → `My Project` |
| `{{key.subkey}}` | Nested value | `{{tech.frontend.framework}}` → `Angular 18` |
| `{{#if key}}...{{/if}}` | Conditional block | Render section only if value is truthy |
| `{{#unless key}}...{{/unless}}` | Inverse conditional | Render section only if value is falsy |
| `{{#include path/to/file.tmpl}}` | Composition include | Render another template inline from `templates/` |
| `{{#include-commented path/to/file.tmpl}}` | Commented include | Render template inline with each line prefixed by `# ` (for TOML comments) |

### Template Locations

- **Universal templates** go in `templates/universal/` — these produce open-standard files that work across all AI platforms.
- **Copilot-specific templates** go in `templates/copilot/` — agents, prompts, copilot-instructions.
- **OpenCode-specific templates** go in `templates/opencode/` — `opencode.json` config and agent wrappers. Outputs land in `.ai/opencode/`. Agent wrappers use the same `{{#include shared/personas/*.md.tmpl}}` pattern as Copilot and share the same `features.agents.*` toggles.
- **Codex CLI templates** go in `templates/codex/` — `config.toml` config and agent role TOML files. Outputs land in `.ai/codex/`. Agent TOMLs embed persona content as TOML comments using `{{#include-commented shared/personas/*.md.tmpl}}` and share the same `features.agents.*` toggles.
- **Shared persona templates** go in `templates/shared/personas/` — canonical persona behavior/content reused by platform wrappers.
- **Adapter templates** go in `templates/adapters/` — thin pointer files for Cursor, Claude Code, Cline, Windsurf.

### Template File Naming

- All templates MUST use the `.tmpl` extension (e.g., `my-skill/SKILL.md.tmpl`)
- The `.tmpl` suffix is stripped during generation to produce the output filename
- Adapter templates map to custom output paths via `ADAPTER_OUTPUT_MAP` in `generate.py`

### Config Variables

All template variables come from `toolkit.config.yaml`. The config schema is documented inline with comments. Key sections:

- `project.*` — name, description, org
- `tech_stack.*` — frontend, backend, databases, cloud, auth, cicd
- `patterns.*` — auth middleware, data isolation, error format, DB conventions
- `domain.*` — industry, compliance, entities, roles
- `conventions.*` — branch patterns, commit format, naming
- `platforms.*` — which platforms to generate for
- `features.*` — which agents/skills/integrations to include

When adding a new template variable:
1. Add the field to `toolkit.config.yaml` with a descriptive comment
2. Add it to both example configs in `setup/examples/` if applicable
3. Use it in your template with `{{section.field}}`
4. If the field is required, add it to `REQUIRED_FIELDS` in `generate.py`

---

## Generator (`setup/generate.py`)

### Architecture

The generator follows this flow:

1. **Load config** — reads YAML, resolves nested keys into a flat context dict
2. **Validate** — checks required fields, platform flags, feature toggles
3. **Render templates** — processes `{{placeholder}}` syntax, conditionals
4. **Write output** — writes rendered files to `.ai/` directory
5. **Write manifest** — records SHA-256 hashes for upgrade tracking

### Key Functions

| Function | Purpose |
|----------|---------|
| `load_config()` | Parse YAML config and build flat context dict |
| `build_context()` | Flatten nested config into `dot.notation` keys |
| `render_template()` | Process `{{placeholder}}` and `{{#if}}` syntax |
| `resolve_include_path()` | Validate and resolve `{{#include ...}}` paths safely |
| `process_includes()` | Expand include directives before placeholder rendering |
| `process_templates()` | Walk template dirs and render all matching files |
| `process_adapters()` | Render platform adapter files with custom output paths |
| `get_toolkit_version()` | Read `VERSION` file + git commit hash |
| `compute_file_hash()` | SHA-256 hash of file contents |
| `classify_output_file()` | Categorize output for upgrade behavior |
| `write_manifest()` | Write `.toolkit-manifest.json` to output dir |

### CLI Flags

```bash
python3 setup/generate.py                          # Standard generation
python3 setup/generate.py --config path/to.yaml    # Custom config file
python3 setup/generate.py --dry-run                # Preview without writing
python3 setup/generate.py --validate               # Validate config only
python3 setup/generate.py --target copilot,cursor   # Specific platforms only
python3 setup/generate.py --target all              # All platforms regardless
```

### Testing Changes

Always test template or generator changes before committing:

```bash
# Quick validation
./setup/generate.sh --validate

# Dry run with example config
./setup/generate.sh --config setup/examples/angular-node-aws.yaml --dry-run

# Full generation with example config (inspect .ai/ output)
./setup/generate.sh --config setup/examples/angular-node-aws.yaml
```

---

## Adding New Components

### Add a Skill

1. Create directory `templates/universal/skills/my-skill/`
2. Create `templates/universal/skills/my-skill/SKILL.md.tmpl`
3. Add `my_skill: true` to `features.skills` in `toolkit.config.yaml`
4. Add reference files to `templates/universal/skills/my-skill/reference/` if needed
5. Update example configs in `setup/examples/`
6. Bump `VERSION` (minor) and add `CHANGELOG.md` entry

### Add an Agent

1. Create `templates/copilot/agents/my-agent.agent.md.tmpl`
2. Add `my_agent: true` to `features.agents` in `toolkit.config.yaml`
3. Update example configs
4. Bump `VERSION` (minor) and add `CHANGELOG.md` entry

### Add a Platform Adapter

1. Create `templates/adapters/my-platform.tmpl`
2. Add entry to `ADAPTER_OUTPUT_MAP` in `generate.py`
3. Add `my_platform: false` to `platforms` in `toolkit.config.yaml`
4. Add symlink logic to `setup/setup-links.sh` if needed
5. Bump `VERSION` (minor) and add `CHANGELOG.md` entry

### Add a Native Platform (OpenCode-style)

Native platforms render full agent definitions from shared personas rather than a single pointer file. Follow the OpenCode implementation as the canonical reference:

1. Create `templates/my-platform/` with a config file template and `agents/*.md.tmpl` wrappers
2. Each agent wrapper uses `{{#include shared/personas/X.md.tmpl}}` plus platform-specific frontmatter
3. Add a `resolve_output_path()` case in `generate.py` to map `my-platform/*` → `.ai/my-platform/*`
4. Add a `should_process_template()` case that gates on `platforms.my_platform` and `features.agents.*` toggles
5. Add `my_platform: false` to `platforms` in `toolkit.config.yaml` and both example configs
6. Add symlink logic to `setup/setup-links.sh`
7. Update `README.md` platform diagram, "Platform Support" table, generated output structure, and toolkit source structure
8. Update `.github/copilot-instructions.md` Template Locations section
9. Bump `VERSION` (minor) and add `CHANGELOG.md` entry

### Add a Context File

1. Add template to `templates/universal/context/My_Context.md.tmpl`
2. Add entry to `context_files` list in `toolkit.config.yaml`
3. Add corresponding structured data template (`.jsonl.tmpl` or `.yaml.tmpl`) if applicable
4. Update the Context Index template
5. Bump `VERSION` (minor) and add `CHANGELOG.md` entry

### Add a Prompt

1. Create `templates/copilot/prompts/my-prompt.prompt.md.tmpl`
2. No config toggle needed — prompts are included when the `copilot` platform is enabled
3. Bump `VERSION` (patch or minor) and add `CHANGELOG.md` entry

---

## File Categories (Upgrade Behavior)

Generated files are classified into categories that determine how they behave during toolkit upgrades:

| Category | Behavior | Examples |
|----------|----------|---------|
| `script` | Auto-regenerated, no user content expected | `.py`, `.sh` files |
| `update-meta` | Auto-regenerated, toolkit-internal docs | `update/` directory |
| `template-output` | Diff review if user has modified; merge carefully | `AGENTS.md`, agents, skills, instructions, adapters |
| `context-stub` | Never touched during upgrade (user-populated) | `context/` directory files |

When adding new templates, ensure `classify_output_file()` in `generate.py` returns the correct category. The default is `template-output`.

---

## Commit Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

Closes #<issue>
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Scopes**: `generator`, `templates`, `skills`, `agents`, `config`, `ci`, `bootstrap`, `adapters`, `opencode`, `codex`

**Examples**:
```
feat(skills): add database-migration skill
fix(generator): handle empty arrays in conditional blocks
docs(readme): add platform adapter extension guide
chore(ci): add version-check workflow
```

---

## Code Quality

### Python (`setup/generate.py`)
- Target Python 3.8+ compatibility (no walrus operators, no `match` statements)
- Only stdlib + `PyYAML` as dependencies — no other third-party packages
- Use type hints (`Dict`, `List`, `Optional` from `typing`)
- Follow PEP 8 style

### Templates
- Keep templates readable — use comments to explain conditional blocks
- Test with both example configs to verify conditional branches
- Ensure templates degrade gracefully when optional fields are empty
- Do not hard-code project-specific values — always use `{{placeholders}}`

### Markdown Output
- Generated markdown should be well-structured with clear headings
- Use tables for structured data
- Include actionable examples, not just descriptions
- Follow accessibility best practices in documentation

---

## PR Checklist

Before submitting a PR, verify:

- [ ] Templates render correctly: `./setup/generate.sh --validate` passes
- [ ] Dry run succeeds: `./setup/generate.sh --config setup/examples/angular-node-aws.yaml --dry-run`
- [ ] Unit tests pass: `cd setup && python3 -m unittest discover -s tests -v`
- [ ] `VERSION` bumped (if templates/setup changed)
- [ ] `CHANGELOG.md` updated under `[Unreleased]` (if templates/setup changed)
- [ ] Example configs updated (if new config fields added)
- [ ] No hard-coded project-specific values in templates

---

## Helpful Commands

```bash
# Validate config schema
./setup/generate.sh --validate

# Run unit tests
cd setup && python3 -m unittest discover -s tests -v

# Dry run with default config
./setup/generate.sh --dry-run

# Generate with a specific example config
./setup/generate.sh --config setup/examples/angular-node-aws.yaml

# Generate for specific platforms only
./setup/generate.sh --target copilot,cursor

# Preview symlinks
bash .ai/setup-links.sh --dry-run

# Clean all symlinks
bash .ai/setup-links.sh --clean

# Check current toolkit version
cat VERSION

# View recent changes
head -50 CHANGELOG.md
```

---

*Last updated: 2026-02-27 · Toolkit version: 0.4.0*
